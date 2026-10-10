# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "CRM & Estimating Overview" tab of the CRM & Estimating workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency.

The figures are the reports' own: opportunity value and weighted value as the
Opportunity Pipeline report computes them, and won / lost / open as the Win
Loss Analysis report decides them, so a number here matches its report.
"""

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, getdate, now_datetime, today

from a3_constructa.a3_constructa.report.opportunity_pipeline.opportunity_pipeline import OPEN_STATUSES
from a3_constructa.a3_constructa.report.opportunity_pipeline.opportunity_pipeline import (
	get_opportunities as pipeline_opportunities,
)
from a3_constructa.a3_constructa.report.win_loss_analysis.win_loss_analysis import get_quotations as decided_quotations
from a3_constructa.api.utils import default_company, default_currency

DUE_DAYS = 14
DUE_SOON_DAYS = 7
EXPIRING_DAYS = 7
IDLE_DAYS = 30
TENDERS_LISTED = 8
# A quotation still in front of the client: submitted, and neither ordered nor lost.
AWAITING = ("Open", "Replied")
QUOTATION_STATUSES = ("Draft", "Pending Management Approval", "Open", "Replied", "Partially Ordered", "Ordered", "Lost", "Expired")


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	company = default_company()
	can_opp = frappe.has_permission("Opportunity", "read")
	can_quote = frappe.has_permission("Quotation", "read")
	opportunities = pipeline_opportunities(frappe._dict(company=company)) if can_opp else None
	quotes = _quotations(company) if can_quote else None
	decided = decided_quotations(frappe._dict(company=company, from_date=str(add_months(now, -12)), to_date=str(now))) if can_quote else None
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"pipeline": _pipeline(opportunities, company),
		"tenders": _tenders(opportunities, now),
		"awaiting": _awaiting(quotes, decided),
		"win_rate": _win_rate(decided, now),
		"by_stage": _by(opportunities, "sales_stage", _("No sales stage"), company),
		"by_sector": _by(opportunities, "sector", _("No sector"), company),
		"quotation_status": _quotation_status(quotes, company),
		"lost_reasons": _lost_reasons(decided),
		"trend": _trend(company, now) if can_quote else {"restricted": True},
		"health": _health(opportunities, quotes, company, now),
	}


def _quotations(company):
	return frappe.get_list(
		"Quotation",
		filters={"company": company, "docstatus": ["<", 2]},
		fields=["name", "docstatus", "status", "workflow_state", "grand_total", "base_grand_total", "valid_till",
		        "transaction_date", "customer_name", "party_name", "opportunity", "margin_percent", "boq"],
		limit_page_length=0,
	)


def _open_filters(company):
	return {"company": company, "status": ["in", list(OPEN_STATUSES)]}


# ---------------------------------------------------------------- summary


def _pipeline(opps, company) -> dict:
	if opps is None:
		return {"restricted": True}
	leads = None
	if frappe.has_permission("Lead", "read"):
		leads = frappe.get_list("Lead", filters={"company": company, "status": ["in", ["Lead", "Open", "Replied", "Interested"]]},
		                        fields=["count(name) as n"])[0].n
	return {
		"restricted": False,
		"count": len(opps),
		"value": sum(o.value for o in opps),
		"weighted": sum(o.weighted for o in opps),
		"leads": leads,
		"filters": _open_filters(company),
	}


def _tenders(opps, now) -> dict:
	if opps is None:
		return {"restricted": True}
	horizon = add_days(now, DUE_DAYS)
	due = sorted([o for o in opps if o.tender_due_date and now <= getdate(o.tender_due_date)], key=lambda o: getdate(o.tender_due_date))
	in_window = [o for o in due if getdate(o.tender_due_date) <= getdate(horizon)]
	return {
		"restricted": False,
		"due_count": len(in_window),
		"unquoted": len([o for o in in_window if not o.quoted]),
		"filters": {"tender_due_date": ["between", [str(now), str(horizon)]], "status": ["in", list(OPEN_STATUSES)]},
		"next": [
			{"name": o.name, "title": o.title or o.customer_name or o.party_name, "client": o.customer_name or o.party_name,
			 "due": o.tender_due_date, "days": (getdate(o.tender_due_date) - now).days, "value": o.value, "quoted": o.quoted,
			 "sector": o.sector}
			for o in due[:TENDERS_LISTED]
		],
	}


def _awaiting(quotes, decided) -> dict:
	if quotes is None:
		return {"restricted": True}
	won = {q.name for q in decided or [] if q.outcome == "Won"}
	rows = [q for q in quotes if q.docstatus == 1 and q.status in AWAITING and q.name not in won]
	return {
		"restricted": False,
		"count": len(rows),
		"value": sum(flt(q.base_grand_total) for q in rows),
		"filters": {"docstatus": 1, "status": ["in", list(AWAITING)], "name": ["in", [q.name for q in rows]]},
	}


def _win_rate(decided, now) -> dict:
	if decided is None:
		return {"restricted": True}
	won = [q for q in decided if q.outcome == "Won"]
	lost = [q for q in decided if q.outcome == "Lost"]
	count = len(won) + len(lost)
	value = sum(flt(q.base_grand_total) for q in won + lost)
	won_value = sum(flt(q.base_grand_total) for q in won)
	return {
		"restricted": False,
		"won": len(won),
		"lost": len(lost),
		"percent": round(len(won) / count * 100, 1) if count else None,
		"value_percent": round(won_value / value * 100, 1) if value else None,
		"won_value": won_value,
		"from_date": str(add_months(now, -12)),
	}


# ---------------------------------------------------------------- breakdowns


def _by(opps, field, empty, company) -> dict:
	if opps is None:
		return {"restricted": True}
	totals = defaultdict(lambda: {"count": 0, "amount": 0.0})
	for o in opps:
		totals[o.get(field) or None]["count"] += 1
		totals[o.get(field) or None]["amount"] += o.value
	rows = sorted(
		[{"label": _(k) if k else empty, "value": k, "count": t["count"], "amount": t["amount"]} for k, t in totals.items()],
		key=lambda r: -r["amount"],
	)
	return {"restricted": False, "rows": rows, "total": sum(r["amount"] for r in rows), "filters": _open_filters(company)}


def _quotation_status(quotes, company) -> dict:
	"""Live quotations by where they stand; a draft waiting for management shows as such.
	Each row carries its quotation names, so its link reproduces the count."""
	if quotes is None:
		return {"restricted": True}
	groups = defaultdict(list)
	for q in quotes:
		if q.docstatus == 0:
			groups["Pending Management Approval" if q.workflow_state == "Pending Management Approval" else "Draft"].append(q.name)
		else:
			groups[q.status].append(q.name)
	rows = [{"label": _(s), "value": ["in", groups[s]], "count": len(groups[s])} for s in QUOTATION_STATUSES if groups.get(s)]
	return {"restricted": False, "rows": rows, "total": sum(r["count"] for r in rows)}


def _lost_reasons(decided) -> dict:
	if decided is None:
		return {"restricted": True}
	lost = [q for q in decided if q.outcome == "Lost"]
	by_reason = defaultdict(list)
	for q in lost:
		for reason in q.reasons or [None]:
			by_reason[reason].append(q.name)
	rows = sorted(
		[{"label": _(r) if r else _("No reason given"), "value": ["in", names], "count": len(names)} for r, names in by_reason.items()],
		key=lambda r: -r["count"],
	)
	return {"restricted": False, "rows": rows, "total": len(lost)}


def _trend(company, now) -> dict:
	"""Won and lost value per month, by quotation date, over the last 12 months."""
	start = get_first_day(add_months(now, -11))
	quotes = decided_quotations(frappe._dict(company=company, from_date=str(start), to_date=str(now)))
	months = []
	for i in range(12):
		first = get_first_day(add_months(start, i))
		months.append({"month": first.strftime("%Y-%m"), "label": first.strftime("%B %Y"), "short": first.strftime("%b"),
		               "won": 0.0, "lost": 0.0, "won_count": 0, "lost_count": 0})
	index = {m["month"]: m for m in months}
	for q in quotes:
		m = index.get(q.month)
		if not m or q.outcome == "Open":
			continue
		key = "won" if q.outcome == "Won" else "lost"
		m[key] += flt(q.base_grand_total)
		m[f"{key}_count"] += 1
	return {"restricted": False, "trend": months}


# ---------------------------------------------------------------- health


def _health(opps, quotes, company, now) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy."""
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append({"label": _(label), "severity": severity, "doctype": doctype, "count": count,
		               "filters": filters or {}, "meta": meta})

	# 1. Tenders due within 7 days with no quotation yet.
	unquoted = None
	if opps is not None:
		soon = getdate(add_days(now, DUE_SOON_DAYS))
		unquoted = [o.name for o in opps if o.tender_due_date and now <= getdate(o.tender_due_date) <= soon and not o.quoted]
	check("Tenders due in 7 days without a quotation", "critical", "Opportunity",
	      len(unquoted) if unquoted is not None else None, {"name": ["in", unquoted or []]},
	      meta=_("Price the tender BOQ and create the quotation"))

	# 2. Quotations below the minimum margin waiting for management.
	pending = None if quotes is None else [q.name for q in quotes if q.docstatus == 0 and q.workflow_state == "Pending Management Approval"]
	check("Quotations below margin awaiting approval", "warning", "Quotation",
	      len(pending) if pending is not None else None, {"workflow_state": "Pending Management Approval", "company": company},
	      meta=_("Management approves or rejects the price"))

	# 3. Quotations in front of the client that expire within 7 days.
	expiring = None
	if quotes is not None:
		end = getdate(add_days(now, EXPIRING_DAYS))
		expiring = [q.name for q in quotes if q.docstatus == 1 and q.status in AWAITING and q.valid_till
		            and now <= getdate(q.valid_till) <= end]
	check("Quotations expiring in 7 days", "warning", "Quotation",
	      len(expiring) if expiring is not None else None, {"name": ["in", expiring or []]},
	      meta=_("Chase the client, or extend the validity"))

	# 4. Open opportunities nobody has touched for 30 days.
	idle = None
	if opps is not None:
		idle_filters = {**_open_filters(company), "modified": ["<", str(add_days(now, -IDLE_DAYS))]}
		idle = frappe.get_list("Opportunity", filters=idle_filters, pluck="name", limit_page_length=0)
	check("Opportunities idle for 30 days", "warning", "Opportunity",
	      len(idle) if idle is not None else None, {"name": ["in", idle or []]},
	      meta=_("No change in a month"))

	# 5. Lost quotations with no lost reason recorded.
	no_reason = None
	if quotes is not None:
		lost = [q.name for q in quotes if q.status == "Lost"]
		with_reason = set(frappe.get_all("Quotation Lost Reason Detail", filters={"parenttype": "Quotation", "parent": ["in", lost or [""]]},
		                                 pluck="parent"))
		no_reason = [n for n in lost if n not in with_reason]
	check("Lost quotations without a reason", "warning", "Quotation",
	      len(no_reason) if no_reason is not None else None, {"name": ["in", no_reason or []]},
	      meta=_("Record why, for the win / loss analysis"))

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
