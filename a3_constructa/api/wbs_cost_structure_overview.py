# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "WBS & Cost Structure Overview" tab of the WBS & Cost Structure workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency.

The approved budget is the budget_amount of the lines of submitted BOQs (an
allowance line holds what is left of the allowance, so the sum counts each
dollar once). Allocated is the submitted WBS Allocations made from those BOQs;
the difference is the unallocated balance the 100% rule keeps visible.
"""

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate, now_datetime, today

from a3_constructa.api.utils import company_projects, default_company, default_currency

DOCTYPES = ("BOQ", "WBS Allocation", "WBS", "Budget Revision Log", "Cost Code")
WBS_STATUSES = ("Draft", "Active", "On Hold", "Completed")
NODE_TYPES = ("Cost Head", "Work Package", "WBS")
RECENT_CHANGES = 8
TOP_HEADS = 6
# Where a WBS node is posted to: the documents P-01A refuses for a non-Active node, and the ledger.
POSTING_LINES = (
	("Material Request", "Material Request Item"),
	("Purchase Order", "Purchase Order Item"),
	("Stock Entry", "Stock Entry Detail"),
	("Timesheet", "Timesheet Detail"),
)


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {dt for dt in DOCTYPES if frappe.has_permission(dt, "read")}
	lines = _boq_lines(readable)
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"allocation": _allocation(readable, lines),
		"wbs": _wbs(readable),
		"changes": _changes(readable, now),
		"budget_by_head": _by_head(readable, lines),
		"budget_by_category": _by_category(readable, lines),
		"health": _health(readable, lines),
	}


def _projects():
	return company_projects(default_company()) or [""]


def _scoped(doctype, filters=None):
	"""`filters` narrowed to the default company's projects, as a list of conditions."""
	if isinstance(filters, dict):
		conditions = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
	else:
		conditions = list(filters or [])
	if frappe.get_meta(doctype).has_field("project"):
		conditions.append([doctype, "project", "in", _projects()])
	return conditions


def _count(doctype, filters=None) -> int:
	return frappe.get_list(doctype, filters=_scoped(doctype, filters), fields=["count(name) as n"])[0].n


# ---------------------------------------------------------------- data


def _boq_lines(readable):
	"""Every line of the company's approved BOQs, with what it is allocated."""
	if "BOQ" not in readable:
		return None
	child = "`tabBOQ Item`"
	lines = frappe.get_list(
		"BOQ",
		filters=_scoped("BOQ", [["BOQ", "docstatus", "=", 1], ["BOQ Item", "name", "is", "set"]]),
		fields=[
			"name as boq", "project", "cost_head", f"{child}.name as line", f"{child}.idx as idx",
			f"{child}.item_code as item_code", f"{child}.description as description", f"{child}.wbs as wbs",
			f"{child}.cost_code as cost_code", f"{child}.is_allowance as is_allowance",
			f"{child}.approved_qty as approved_qty", f"{child}.budget_amount as budget",
			f"{child}.amount as amount", f"{child}.allowance_used as allowance_used",
		],
		limit_page_length=0,
	)
	held = defaultdict(lambda: {"qty": 0.0, "amount": 0.0, "submitted": 0.0})
	if "WBS Allocation" in readable and lines:
		for row in frappe.get_list(
			"WBS Allocation",
			filters=[["WBS Allocation", "docstatus", "<", 2], ["WBS Allocation Item", "boq_item", "in", [l.line for l in lines]]],
			fields=["docstatus", "`tabWBS Allocation Item`.boq_item as line", "`tabWBS Allocation Item`.allocated_qty as qty",
			        "`tabWBS Allocation Item`.allocated_amount as amount"],
			limit_page_length=0,
		):
			held[row.line]["qty"] += flt(row.qty)
			held[row.line]["amount"] += flt(row.amount)
			if row.docstatus == 1:
				held[row.line]["submitted"] += flt(row.amount)
	for line in lines:
		h = held[line.line]
		line.allocated = h["submitted"]
		if line.is_allowance:
			line.left = flt(line.budget) - h["amount"]
		else:
			line.left = flt(line.approved_qty) - h["qty"]
	return lines


def _allocation(readable, lines) -> dict:
	if lines is None or "WBS Allocation" not in readable:
		return {"restricted": True}
	approved = sum(flt(l.budget) for l in lines)
	allocated = sum(flt(l.allocated) for l in lines)
	open_lines = [l for l in lines if l.left > 0.0005]
	return {
		"restricted": False,
		"approved": approved,
		"allocated": allocated,
		"unallocated": approved - allocated,
		"percent": round(allocated / approved * 100, 1) if approved else None,
		"boqs": len({l.boq for l in lines}),
		"lines_open": len(open_lines),
		"allowances_left": sum(flt(l.left) for l in open_lines if l.is_allowance),
	}


def _wbs(readable) -> dict:
	if "WBS" not in readable:
		return {"restricted": True}
	nodes = frappe.get_list("WBS", filters=_scoped("WBS"), fields=["name", "status", "node_type"], limit_page_length=0)
	statuses = Counter(n.status for n in nodes)
	types = Counter(n.node_type for n in nodes)
	return {
		"restricted": False,
		"total": len(nodes),
		"active": statuses.get("Active", 0),
		"by_status": [{"label": _(s), "value": s, "count": statuses[s]} for s in WBS_STATUSES if statuses.get(s)],
		"by_type": [{"label": _(t), "value": t, "count": types[t]} for t in NODE_TYPES if types.get(t)],
		"filters": {"project": ["in", _projects()]},
	}


def _changes(readable, now) -> dict:
	if "Budget Revision Log" not in readable:
		return {"restricted": True}
	start = get_first_day(add_months(now, -11))
	rows = frappe.get_list(
		"Budget Revision Log",
		filters=_scoped("Budget Revision Log", {"posted_on": [">=", str(start)]}),
		fields=["name", "posted_on", "change_type", "amount", "wbs", "cost_code", "reference_doctype", "reference_name", "reason"],
		order_by="posted_on desc",
		limit_page_length=0,
	)
	months = []
	for i in range(12):
		first = get_first_day(add_months(start, i))
		key = first.strftime("%Y-%m")
		months.append({"month": key, "label": first.strftime("%B %Y"), "short": first.strftime("%b"), "added": 0.0, "removed": 0.0, "count": 0})
	index = {m["month"]: m for m in months}
	for r in rows:
		m = index.get(getdate(r.posted_on).strftime("%Y-%m"))
		if not m:
			continue
		m["count"] += 1
		if flt(r.amount) >= 0:
			m["added"] += flt(r.amount)
		else:
			m["removed"] += flt(r.amount)
	this_month = index[now.strftime("%Y-%m")]
	return {
		"restricted": False,
		"trend": months,
		"this_month": {"count": this_month["count"], "net": this_month["added"] + this_month["removed"],
		               "filters": {"posted_on": [">=", str(get_first_day(now))]}},
		"recent": [
			{key: r[key] for key in ("name", "posted_on", "change_type", "amount", "wbs", "cost_code", "reference_doctype", "reference_name", "reason")}
			for r in rows[:RECENT_CHANGES]
		],
	}


def _by_head(readable, lines) -> dict:
	if lines is None:
		return {"restricted": True}
	totals = defaultdict(lambda: {"amount": 0.0, "boqs": set()})
	for l in lines:
		totals[l.cost_head]["amount"] += flt(l.budget)
		totals[l.cost_head]["boqs"].add(l.boq)
	names = dict(frappe.get_list("Cost Head", fields=["name", "cost_head_name"], as_list=True, limit_page_length=0)) if frappe.has_permission("Cost Head", "read") else {}
	rows = sorted(
		[{"label": f"{names.get(h) or h} ({h})" if h else _("No cost head"), "value": h, "count": len(t["boqs"]), "amount": t["amount"]}
		 for h, t in totals.items()],
		key=lambda r: -r["amount"],
	)
	if len(rows) > TOP_HEADS:
		rest = rows[TOP_HEADS:]
		rows = rows[:TOP_HEADS] + [{"label": _("Other"), "value": None, "other": True,
		                             "count": sum(r["count"] for r in rest), "amount": sum(r["amount"] for r in rest)}]
	return {"restricted": False, "rows": rows, "total": sum(r["amount"] for r in rows), "filters": {"docstatus": 1, "project": ["in", _projects()]}}


def _by_category(readable, lines) -> dict:
	if lines is None or "Cost Code" not in readable:
		return {"restricted": True}
	category = dict(frappe.get_list("Cost Code", fields=["name", "category"], as_list=True, limit_page_length=0))
	totals = defaultdict(lambda: {"amount": 0.0, "codes": set()})
	for l in lines:
		cat = category.get(l.cost_code) if l.cost_code else None
		totals[cat]["amount"] += flt(l.budget)
		if l.cost_code:
			totals[cat]["codes"].add(l.cost_code)
	rows = sorted(
		[{"label": _(c) if c else _("No category"), "value": c, "count": len(t["codes"]), "amount": t["amount"]} for c, t in totals.items()],
		key=lambda r: -r["amount"],
	)
	return {"restricted": False, "rows": rows, "total": sum(r["amount"] for r in rows)}


# ---------------------------------------------------------------- health


def _health(readable, lines) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for money booked to a node that is not open for it."""
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None, report=None):
		checks.append({"label": _(label), "severity": severity, "doctype": doctype, "count": count,
		               "filters": filters or {}, "meta": meta, "report": report})

	# 1. Postings to non-Active WBS nodes: draft requests, orders, issues or
	# timesheets still booked to a node that has since been put on hold, closed,
	# or never opened. P-01A refuses to save them, so they are stuck until rebooked.
	posted = None
	if "WBS" in readable:
		closed_nodes = frappe.get_list("WBS", filters=_scoped("WBS", {"status": ["!=", "Active"]}), pluck="name", limit_page_length=0)
		posted = set()
		for parent, child in POSTING_LINES:
			if closed_nodes and frappe.has_permission(parent, "read"):
				posted.update(_draft_values(parent, child, "wbs", closed_nodes))
		posted = sorted(posted)
	check("Stopped WBS nodes with draft documents", "critical", "WBS",
	      len(posted) if posted is not None else None, {"name": ["in", posted or []]},
	      meta=_("Rebook the drafts to an Active node, or reopen the node"))

	# 2. Unallocated BOQ lines (the 100% rule's open balance).
	open_lines = None if lines is None else [l for l in lines if l.left > 0.0005]
	check("Approved BOQ lines not fully allocated to WBS", "warning", "BOQ",
	      len(open_lines) if open_lines is not None else None,
	      {"company": default_company()}, meta=_("Unallocated BOQ Lines report"), report="Unallocated BOQ Lines")

	# 3. WBS without a responsible person.
	no_owner = {"responsible_person": ["is", "not set"], "status": ["in", ["Draft", "Active", "On Hold"]]}
	check("Open WBS nodes without a responsible person", "warning", "WBS",
	      _count("WBS", no_owner) if "WBS" in readable else None, {**no_owner, "project": ["in", _projects()]})

	# 4. Inactive cost codes still in use on approved BOQ lines or draft documents.
	inactive_used = None
	if "Cost Code" in readable:
		inactive = frappe.get_list("Cost Code", filters={"status": "Inactive"}, pluck="name", limit_page_length=0)
		inactive_used = set()
		if inactive:
			if lines is not None:
				inactive_used.update(l.cost_code for l in lines if l.cost_code in inactive)
			for parent, child in POSTING_LINES:
				if frappe.has_permission(parent, "read"):
					inactive_used.update(_draft_values(parent, child, "cost_code", inactive))
		inactive_used = sorted(inactive_used)
	check("Inactive cost codes still in use", "warning", "Cost Code",
	      len(inactive_used) if inactive_used is not None else None, {"name": ["in", inactive_used or []]},
	      meta=_("On an approved BOQ line or a draft document"))

	# 5. Overspent allowances: lines drawing from an allowance, plus what is
	# allocated from it, come to more than the allowance.
	overspent = None
	if lines is not None:
		overspent = sorted({l.boq for l in lines if l.is_allowance and flt(l.allowance_used) + flt(l.budget) - flt(l.left) > flt(l.amount) + 0.005})
	check("BOQs with an overspent allowance", "critical", "BOQ",
	      len(overspent) if overspent is not None else None, {"name": ["in", overspent or []]},
	      meta=_("Drawn and allocated beyond the allowance"))

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))


def _draft_values(parent, child, field, values):
	"""The `field` values among `values` used on lines of draft `parent` documents of the company."""
	conditions = [[parent, "docstatus", "=", 0], [child, field, "in", values]]
	if frappe.get_meta(parent).has_field("company") and default_company():
		conditions.append([parent, "company", "=", default_company()])
	return {r.value for r in frappe.get_list(parent, filters=conditions, fields=[f"`tab{child}`.{field} as value"], limit_page_length=0)}
