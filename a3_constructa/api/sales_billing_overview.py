# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Sales & Billing Overview" tab of the Sales & Billing workspace.

Same contract as the other overviews: one call, every figure through
`frappe.get_list` (scoped to the user's default company), a section the caller
cannot read comes back `restricted`, money in the company's currency.

- Headline: what the clients owe (open invoices) plus what they have certified
  and we have not yet invoiced (certified IPCs' net due).
- KPIs: billed this month, retention the clients hold, advance still to recover.
- Checks: overdue invoices, certified IPCs not invoiced, IPCs with the client
  over 21 days, milestones due and not billed, guarantees expiring in 30 days,
  retention due for release.
- Breakdowns: billing by award and receivable ageing; IPCs by status and
  retention by award; billed against collected per month.

The receivable and its ageing are the Finance & Accounting overview's own, so the
two tabs never disagree.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, getdate, now_datetime, today

from a3_constructa.api import finance_accounting_overview as fa
from a3_constructa.api.utils import default_company, default_currency

DOCTYPES = ("Sales Invoice", "Client IPC", "Awarded Quotation", "Bank Guarantee", "Payment Entry")
IPC_STATUSES = ("Draft", "Submitted to Client", "Certified", "Invoiced")
IPC_WAIT_DAYS = 21
GUARANTEE_DAYS = 30
TOP_AWARDS = 6
RECENT = 8
LIVE_AWARDS = ("Awarded", "In Progress", "On Hold", "Completed")


def _can_read(doctype):
	return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, "read")


def _list(doctype, filters=None, **kwargs):
	return frappe.get_list(doctype, filters=fa._scoped(doctype, filters), limit_page_length=0, **kwargs)


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	currency = default_currency()
	readable = {d for d in DOCTYPES if _can_read(d)}
	invoices = _invoices(readable)
	ipcs = _ipcs(readable)
	retention = _retention(readable, ipcs, invoices)
	return {
		"generated_at": now_datetime(),
		"currency": currency,
		"receivable": fa._ledger("Sales Invoice", "customer", fa._open_invoices("Sales Invoice", "customer", readable, now, currency), now),
		"ipcs": _ipc_summary(ipcs),
		"billing": _billing(invoices, now),
		"retention": retention,
		"advance": _advance(readable, ipcs, invoices),
		"recent": _recent(invoices),
		"trend": _trend(readable, now),
		"health": _health(readable, now, ipcs, retention),
	}


# ---------------------------------------------------------------- sources

def _invoices(readable):
	if "Sales Invoice" not in readable:
		return None
	return _list("Sales Invoice", {"docstatus": 1},
	             fields=["name", "customer", "customer_name", "posting_date", "net_total", "grand_total", "outstanding_amount",
	                     "awarded_quotation", "is_advance_invoice", "is_retention_release", "client_ipc", "final_account", "is_return"],
	             order_by="posting_date desc, name desc")


def _ipcs(readable):
	if "Client IPC" not in readable:
		return None
	return _list("Client IPC", {"docstatus": ["<", 2]},
	             fields=["name", "ipc_no", "awarded_quotation", "status", "docstatus", "claimed_amount", "certified_amount", "net_due",
	                     "retention_this_period", "advance_recovered_this_period", "sales_invoice", "submitted_on", "period_to"])


def _award_titles(names):
	names = [n for n in names if n]
	if not names or not _can_read("Awarded Quotation"):
		return {}
	return {a.name: a.title for a in frappe.get_list("Awarded Quotation", filters={"name": ["in", names]}, fields=["name", "title"],
	                                                limit_page_length=0)}


# ---------------------------------------------------------------- sections

def _ipc_summary(ipcs):
	if ipcs is None:
		return {"restricted": True}
	by_status = []
	for status in IPC_STATUSES:
		rows = [r for r in ipcs if r.status == status]
		if rows:
			amount = sum(flt(r.certified_amount if r.docstatus == 1 else r.claimed_amount) for r in rows)
			by_status.append({"label": _(status), "value": status, "count": len(rows), "amount": amount})
	unbilled = [r for r in ipcs if r.docstatus == 1 and r.status == "Certified" and not r.sales_invoice]
	return {
		"restricted": False,
		"by_status": by_status,
		"filters": fa._listed({"docstatus": ["<", 2]}),
		"certified_unbilled": sum(flt(r.net_due) for r in unbilled),
		"certified_unbilled_count": len(unbilled),
		"with_client": sum(flt(r.claimed_amount) for r in ipcs if r.status == "Submitted to Client"),
	}


def _kind(row, opening=()):
	if row.is_return:
		return _("Credit note")
	if row.is_advance_invoice:
		return _("Advance")
	if row.is_retention_release:
		return _("Retention release")
	if row.final_account:
		return _("Final account")
	if row.client_ipc or row.name in opening:
		return _("IPC")
	if row.awarded_quotation:
		return _("Milestone")
	return _("Invoice")


def _billing(invoices, now):
	if invoices is None:
		return {"restricted": True}
	first = get_first_day(now)
	month = [r for r in invoices if getdate(r.posting_date) >= first]
	groups = {}
	for r in invoices:
		g = groups.setdefault(r.awarded_quotation, {"value": r.awarded_quotation, "count": 0, "amount": 0.0})
		g["count"] += 1
		g["amount"] += flt(r.net_total)
	titles = _award_titles(list(groups))
	for key, g in groups.items():
		g["label"] = f"{titles.get(key) or key}" if key else _("Not linked to an award")
	return {
		"restricted": False,
		"month_amount": sum(flt(r.net_total) for r in month),
		"month_count": len(month),
		"month_label": first.strftime("%B %Y"),
		"total": sum(flt(r.net_total) for r in invoices),
		"by_award": fa._top(list(groups.values()), TOP_AWARDS, measure="amount"),
		"filters": fa._listed({"docstatus": 1}),
	}


def _retention(readable, ipcs, invoices):
	if ipcs is None or invoices is None:
		return {"restricted": True}
	from a3_constructa.api.client_billing import release_due

	held = defaultdict(float)
	documents = defaultdict(int)
	for r in ipcs:
		if r.docstatus == 1 and flt(r.retention_this_period):
			held[r.awarded_quotation] += flt(r.retention_this_period)
			documents[r.awarded_quotation] += 1
	released = defaultdict(float)
	for r in invoices:
		if r.is_retention_release:
			released[r.awarded_quotation] += flt(r.net_total)
	titles = _award_titles(list(held))
	rows, due = [], []
	for award, amount in held.items():
		balance = flt(amount - released[award], 2)
		rows.append({"label": titles.get(award) or award, "value": award, "count": documents[award], "amount": balance})
		if balance > 0.005 and "Awarded Quotation" in readable:
			a = frappe.get_doc("Awarded Quotation", award)
			if any(release_due(a, half) is None for half in (1, 2)):
				due.append({"award": award, "amount": balance})
	return {
		"restricted": False,
		"held": sum(held.values()),
		"released": sum(released.values()),
		"balance": sum(r["amount"] for r in rows),
		"by_award": sorted([r for r in rows if r["amount"] > 0.005], key=lambda r: -r["amount"]),
		"filters": fa._listed({"docstatus": 1}),
		"due": due,
	}


def _advance(readable, ipcs, invoices):
	if ipcs is None or invoices is None:
		return {"restricted": True}
	advances = [r for r in invoices if r.is_advance_invoice]
	billed = sum(flt(r.net_total) for r in advances)
	recovered = sum(flt(r.advance_recovered_this_period) for r in ipcs if r.docstatus == 1)
	finals = [r.name for r in invoices if r.final_account]
	if finals:
		recovered -= flt(sum(t.tax_amount for t in frappe.get_all("Sales Taxes and Charges",
			filters={"parent": ["in", finals], "parenttype": "Sales Invoice", "a3_deduction": 1, "account_head": ["like", "Advances from Customers%"]},
			fields=["tax_amount"])))
	return {
		"restricted": False,
		"billed": billed,
		"recovered": recovered,
		"outstanding": flt(billed - recovered, 2),
		"awards": len({r.awarded_quotation for r in advances}),
	}


def _recent(invoices):
	if invoices is None:
		return {"restricted": True}
	rows = invoices[:RECENT]
	titles = _award_titles([r.awarded_quotation for r in rows])
	# A claim invoiced before certificates were kept, which an opening IPC records.
	opening = set(frappe.get_all("Client IPC", filters={"docstatus": 1, "opening_invoice": ["in", [r.name for r in rows] or [""]]},
	                             pluck="opening_invoice"))
	return {
		"restricted": False,
		"list": [{"name": r.name, "customer": r.customer_name or r.customer, "kind": _kind(r, opening), "award": r.awarded_quotation,
		          "award_title": titles.get(r.awarded_quotation), "amount": flt(r.grand_total), "outstanding": flt(r.outstanding_amount),
		          "posting_date": r.posting_date} for r in rows],
	}


def _trend(readable, now):
	"""Per month: invoiced (VAT included, credit notes net) against cash received from customers."""
	if "Sales Invoice" not in readable and "Payment Entry" not in readable:
		return {"restricted": True}
	start = get_first_day(add_months(now, -11))
	months = []
	for i in range(12):
		first = get_first_day(add_months(start, i))
		months.append({"month": first.strftime("%Y-%m"), "label": first.strftime("%B %Y"), "short": first.strftime("%b"),
		               "billed": 0.0, "collected": 0.0, "billed_count": 0, "collected_count": 0})
	index = {m["month"]: m for m in months}
	if "Sales Invoice" in readable:
		for r in _list("Sales Invoice", {"docstatus": 1, "posting_date": [">=", str(start)]}, fields=["posting_date", "base_grand_total"]):
			m = index.get(getdate(r.posting_date).strftime("%Y-%m"))
			if m:
				m["billed"] += flt(r.base_grand_total)
				m["billed_count"] += 1
	if "Payment Entry" in readable:
		for r in _list("Payment Entry", {"docstatus": 1, "payment_type": "Receive", "party_type": "Customer", "posting_date": [">=", str(start)]},
		               fields=["posting_date", "base_received_amount"]):
			m = index.get(getdate(r.posting_date).strftime("%Y-%m"))
			if m:
				m["collected"] += flt(r.base_received_amount)
				m["collected_count"] += 1
	return {"restricted": False, "trend": months}


# ---------------------------------------------------------------- checks

def _health(readable, now, ipcs, retention) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy."""
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append({"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta})

	overdue = {"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", str(now)]}
	rows = _list("Sales Invoice", overdue, fields=["outstanding_amount"]) if "Sales Invoice" in readable else None
	check("Invoices past their due date", "critical", "Sales Invoice", len(rows) if rows is not None else None, fa._listed(overdue),
	      _("{0} overdue").format(frappe.format(sum(flt(r.outstanding_amount) for r in rows), {"fieldtype": "Currency", "options": default_currency()}))
	      if rows else None)

	unbilled = {"docstatus": 1, "status": "Certified"}
	n = len([r for r in ipcs if r.docstatus == 1 and r.status == "Certified" and not r.sales_invoice]) if ipcs is not None else None
	check("Certified IPCs not yet invoiced", "critical", "Client IPC", n, fa._listed(unbilled), _("Certified by the client: invoice them"))

	cutoff = add_days(now, -IPC_WAIT_DAYS)
	waiting = {"docstatus": 0, "status": "Submitted to Client", "submitted_on": ["<", str(cutoff)]}
	n = len([r for r in ipcs if r.docstatus == 0 and r.status == "Submitted to Client" and r.submitted_on
	         and getdate(r.submitted_on) < cutoff]) if ipcs is not None else None
	check("IPCs not certified after 21 days", "critical", "Client IPC", n, fa._listed(waiting), _("With the client's engineer for over three weeks"))

	due_awards = []
	n = None
	if "Awarded Quotation" in readable:
		from a3_constructa.api.milestone_billing import is_due

		n = 0
		for a in frappe.get_list("Awarded Quotation", filters=fa._scoped("Awarded Quotation", {"status": ["in", LIVE_AWARDS]}),
		                         fields=["name", "billing_basis"], limit_page_length=0):
			rows = frappe.get_all("Awarded Quotation Milestone", filters={"parent": a.name, "parenttype": "Awarded Quotation"},
			                      fields=["actual_end", "billing_percent", "sales_invoice"])
			due = [r for r in rows if is_due(a, r)]
			if due:
				n += len(due)
				due_awards.append(a.name)
	check("Milestones due and not billed", "warning", "Awarded Quotation", n, {"name": ["in", due_awards]},
	      (_("On 1 award") if len(due_awards) == 1 else _("Across {0} awards").format(len(due_awards))) if due_awards else _("Use Bill due milestones"))

	expiring = {"docstatus": 1, "end_date": ["between", [str(now), str(add_days(now, GUARANTEE_DAYS))]]}
	rows = _list("Bank Guarantee", expiring, fields=["name"]) if "Bank Guarantee" in readable else None
	check("Guarantees expiring in 30 days", "warning", "Bank Guarantee", len(rows) if rows is not None else None, expiring,
	      _("Extend or release them with the bank"))

	due = None if retention.get("restricted") else retention["due"]
	check("Retention due for release", "warning", "Awarded Quotation", len(due) if due is not None else None,
	      {"name": ["in", [d["award"] for d in due or []]]},
	      _("{0} the client can pay back").format(frappe.format(sum(d["amount"] for d in due), {"fieldtype": "Currency", "options": default_currency()}))
	      if due else _("Practical completion or the end of the defects period reached"))

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
