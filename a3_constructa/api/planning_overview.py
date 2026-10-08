# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Planning & Budgeting Overview" tab of the Planning & Budgeting workspace.

Same contract as master_data_overview: one call returns everything the
dashboard draws, every figure goes through `frappe.get_list` so the caller's
permissions apply, and a section the caller cannot read comes back
`restricted` instead of with numbers.

Money is only ever added up in the company's default currency. An award or
variation priced in another currency is left out of the totals and counted in
`other_currency`, so the page can say so rather than add dirhams to dollars.
BOQ and WBS figures are summed as the budget reports sum them.
"""

from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, now_datetime, today

from a3_constructa.a3_constructa.doctype.awarded_quotation.awarded_quotation import ACTIVE_STATUSES
from a3_constructa.api.utils import company_projects, default_company, default_currency

DOCTYPES = (
	"Awarded Quotation",
	"BOQ",
	"WBS Allocation",
	"Variation Order",
	"Deliverable",
	"Procurement Plan",
	"Project",
)

AWARD_STATUSES = ("Draft", "Awarded", "In Progress", "On Hold", "Completed", "Cancelled")
BOQ_STATUSES = ("Draft", "Pending Approval", "Approved", "Rejected")
VO_STATUSES = ("Draft", "Submitted to Client", "Approved", "Rejected", "Cancelled")
VO_PENDING = ("Draft", "Submitted to Client")
DELIVERABLE_STATUSES = ("Not Started", "In Progress", "Submitted", "Revise and Resubmit", "Approved", "Rejected")
# Deliverable statuses where the next move is ours. A Submitted one is with the client.
DELIVERABLE_OPEN = ("Not Started", "In Progress", "Revise and Resubmit", "Rejected")

PLAN_CLOSED = ("Cancelled", "Completed")
PLAN_STATUSES = ("Draft", "Submitted", "Completed", "Cancelled")
ROUTES = ("Buy", "Hire", "Subcontract")
PLAN_WINDOW_DAYS = 14

TIMELINE_AWARDS = 8
BUDGET_PROJECTS = 6
LIST_LIMIT = 8
MILESTONE_WINDOW_DAYS = 30
DELIVERABLE_WINDOW_DAYS = 14


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	currency = default_currency()
	readable = {doctype for doctype in DOCTYPES if _can_read(doctype)}

	awards = _awards(readable, currency, now)
	budget = _budget(readable)
	plan = _plan(readable, now)

	# Milestones, deliverables and the order book are Contracts & Awards' to show
	# (D-03). The award timeline stays here as the programme view; it only borrows
	# the overdue-milestone count for each bar's warning.
	if not awards["restricted"]:
		overdue = _milestones(readable, now)["overdue_by_award"]
		for award in awards["timeline"]:
			award["overdue_milestones"] = overdue.get(award["name"], 0)

	return {
		"generated_at": now_datetime(),
		"currency": currency,
		"awards": awards,
		"budget": budget,
		"plan": plan,
		"variations": _variations(readable, currency),
		"health": _health(readable, now, budget, plan),
	}


def _can_read(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, "read")


def _count(doctype: str, filters=None) -> int:
	return _get_list(doctype, filters=filters, fields=["count(name) as n"])[0].n


def _joined(child: str) -> list:
	"""A filter every row of `child` passes. `get_list` only joins a child table
	when a filter names it; an aggregate in `fields` alone is not enough."""
	return [child, "name", "is", "set"]


def _in_order(rows, order, count_key="n", value_key=None) -> list[dict]:
	"""Group-by rows as bar-list rows, in the doctype's own status order."""
	found = {row.status: row for row in rows}
	result = []
	for status in order:
		row = found.get(status)
		if row and row.get(count_key):
			entry = {"label": _(status), "value": status, "count": row.get(count_key)}
			if value_key:
				entry["amount"] = flt(row.get(value_key))
			result.append(entry)
	return result


# ---------------------------------------------------------------- sections


def _awards(readable: set, currency: str, now) -> dict:
	if "Awarded Quotation" not in readable:
		return {"restricted": True}

	active = _get_list(
		"Awarded Quotation",
		filters={"status": ["in", ACTIVE_STATUSES]},
		fields=[
			"name",
			"title",
			"customer",
			"status",
			"currency",
			"contract_value",
			"approved_variations",
			"revised_contract_value",
			"start_date",
			"end_date",
			"revised_end_date",
			"progress_percent",
		],
		order_by="revised_contract_value desc",
		limit_page_length=0,
	)
	in_currency = [a for a in active if (a.currency or currency) == currency]
	statuses = _get_list("Awarded Quotation", fields=["status", "count(name) as n"], group_by="status")

	timeline = []
	for award in active[:TIMELINE_AWARDS]:
		end = award.revised_end_date or award.end_date
		timeline.append(
			{
				"name": award.name,
				"title": award.title,
				"customer": award.customer,
				"status": award.status,
				"currency": award.currency or currency,
				"value": flt(award.revised_contract_value),
				"start": award.start_date,
				"end": end,
				"original_end": award.end_date,
				"progress": flt(award.progress_percent),
				"days_late": date_diff(now, end) if end and getdate(end) < now else 0,
			}
		)

	order_book = sum(flt(a.revised_contract_value) for a in in_currency)
	delivered = sum(flt(a.revised_contract_value) * flt(a.progress_percent) / 100 for a in in_currency)

	return {
		"restricted": False,
		"active_count": len(active),
		"total_count": sum(s.n for s in statuses),
		"order_book": order_book,
		# Milestone progress weighted by contract value, so a large job counts for more.
		"weighted_progress": delivered / order_book * 100 if order_book else 0,
		"original_value": sum(flt(a.contract_value) for a in in_currency),
		"approved_variations": sum(flt(a.approved_variations) for a in in_currency),
		"other_currency": len(active) - len(in_currency),
		"by_status": _in_order(statuses, AWARD_STATUSES),
		"timeline": timeline,
	}


def _milestones(readable: set, now) -> dict:
	empty = {"restricted": True, "overdue_by_award": Counter()}
	if "Awarded Quotation" not in readable:
		return empty

	child = "`tabAwarded Quotation Milestone`"
	rows = _get_list(
		"Awarded Quotation",
		filters=[["Awarded Quotation", "status", "in", ACTIVE_STATUSES], _joined("Awarded Quotation Milestone")],
		fields=[
			"name as award",
			"title as award_title",
			f"{child}.milestone as milestone",
			f"{child}.planned_end as planned_end",
			f"{child}.status as status",
		],
		limit_page_length=0,
	)
	open_rows = [r for r in rows if r.status != "Completed" and r.planned_end]
	overdue = sorted((r for r in open_rows if getdate(r.planned_end) < now), key=lambda r: getdate(r.planned_end))
	horizon = getdate(add_days(now, MILESTONE_WINDOW_DAYS))
	upcoming = sorted(
		(r for r in open_rows if now <= getdate(r.planned_end) <= horizon), key=lambda r: getdate(r.planned_end)
	)

	return {
		"restricted": False,
		"total": len(rows),
		"completed": sum(r.status == "Completed" for r in rows),
		"overdue_count": len(overdue),
		"upcoming_count": len(upcoming),
		"window_days": MILESTONE_WINDOW_DAYS,
		"list": [
			{
				"award": r.award,
				"award_title": r.award_title,
				"milestone": r.milestone,
				"planned_end": r.planned_end,
				"days": date_diff(r.planned_end, now),
			}
			for r in (overdue + upcoming)[:LIST_LIMIT]
		],
		"overdue_by_award": Counter(r.award for r in overdue),
	}


def _budget(readable: set) -> dict:
	if "BOQ" not in readable:
		return {"restricted": True}

	statuses = _get_list(
		"BOQ", fields=["status", "count(name) as n", "sum(total_amount) as value"], group_by="status"
	)
	approved = [["BOQ", "docstatus", "=", 1], ["BOQ", "status", "=", "Approved"]]
	approved_boqs = _get_list("BOQ", filters=approved, pluck="name")
	budgets = {
		row.project: flt(row.budget)
		for row in _get_list(
			"BOQ",
			filters=approved + [_joined("BOQ Item")],
			fields=["project", "sum(`tabBOQ Item`.budget_amount) as budget"],
			group_by="project",
		)
	}

	# What of the approved budget sits on the works. A line on a leaf WBS already
	# does; a line on a group WBS (or on none) does only as far as WBS Allocation
	# has split it down. The rest is the unallocated balance the client's rule
	# keeps visible: parent budget = child allocations + unallocated balance.
	allocated = {}
	unallocated_lines = []
	can_allocate = "WBS Allocation" in readable
	if can_allocate and approved_boqs:
		leaves = set(_get_list("WBS", filters={"is_group": 0}, pluck="name", limit_page_length=0))
		split = {}
		for row in _get_list(
			"WBS Allocation",
			filters=[["WBS Allocation", "boq", "in", approved_boqs], ["WBS Allocation", "docstatus", "<", 2],
			         _joined("WBS Allocation Item")],
			fields=["`tabWBS Allocation Item`.boq_item as boq_item", "`tabWBS Allocation Item`.allocated_amount as amount"],
			limit_page_length=0,
		):
			split[row.boq_item] = split.get(row.boq_item, 0) + flt(row.amount)
		for line in _get_list(
			"BOQ",
			filters=approved + [_joined("BOQ Item")],
			fields=["name as boq", "project", "`tabBOQ Item`.name as boq_item", "`tabBOQ Item`.wbs as wbs",
			        "`tabBOQ Item`.budget_amount as budget"],
			limit_page_length=0,
		):
			on_works = flt(line.budget) if line.wbs in leaves else min(flt(line.budget), split.get(line.boq_item, 0))
			allocated[line.project] = allocated.get(line.project, 0) + on_works
			if flt(line.budget) - on_works > 0.01:
				unallocated_lines.append(line)

	titles = {}
	if "Project" in readable and budgets:
		titles = dict(
			_get_list(
				"Project", filters={"name": ["in", list(budgets)]}, fields=["name", "project_name"], as_list=True
			)
		)
	projects = sorted(
		(
			{
				"project": project,
				"label": titles.get(project) or project,
				"budget": budget,
				"allocated": allocated.get(project, 0.0),
			}
			for project, budget in budgets.items()
		),
		key=lambda p: -p["budget"],
	)

	return {
		"restricted": False,
		"approved_budget": sum(budgets.values()),
		"allocated": sum(allocated.values()),
		"allocation_restricted": not can_allocate,
		"approved_count": len(approved_boqs),
		"pending_count": next((s.n for s in statuses if s.status == "Pending Approval"), 0),
		"by_status": _in_order(statuses, BOQ_STATUSES, value_key="value"),
		"projects": projects[:BUDGET_PROJECTS],
		"unallocated_lines": len(unallocated_lines) if can_allocate else None,
		"unallocated_boqs": sorted({line.boq for line in unallocated_lines}) if can_allocate else None,
	}


def _variations(readable: set, currency: str) -> dict:
	if "Variation Order" not in readable:
		return {"restricted": True}

	rows = _get_list(
		"Variation Order",
		fields=["status", "currency", "count(name) as n", "sum(total_amount) as value"],
		group_by="status, currency",
	)
	by_status = {}
	other_currency = 0
	for row in rows:
		entry = by_status.setdefault(row.status, frappe._dict(status=row.status, n=0, value=0.0))
		entry.n += row.n
		if (row.currency or currency) == currency:
			entry.value += flt(row.value)
		else:
			other_currency += row.n

	def total(statuses, key):
		return sum(by_status[s][key] for s in statuses if s in by_status)

	return {
		"restricted": False,
		"approved_value": total(["Approved"], "value"),
		"approved_count": total(["Approved"], "n"),
		"pending_value": total(VO_PENDING, "value"),
		"pending_count": total(VO_PENDING, "n"),
		"other_currency": other_currency,
		"by_status": _in_order(by_status.values(), VO_STATUSES, value_key="value"),
	}


def _deliverables(readable: set, now) -> dict:
	if "Deliverable" not in readable:
		return {"restricted": True}

	statuses = _get_list("Deliverable", fields=["status", "count(name) as n"], group_by="status")
	open_filter = {"status": ["in", DELIVERABLE_OPEN]}
	return {
		"restricted": False,
		"total": sum(s.n for s in statuses),
		"overdue": _count("Deliverable", {**open_filter, "due_date": ["<", now]}),
		"due_soon": _count(
			"Deliverable", {**open_filter, "due_date": ["between", [now, add_days(now, DELIVERABLE_WINDOW_DAYS)]]}
		),
		"window_days": DELIVERABLE_WINDOW_DAYS,
		"awaiting_client": next((s.n for s in statuses if s.status == "Submitted"), 0),
		"by_status": _in_order(statuses, DELIVERABLE_STATUSES),
	}


def _plan(readable: set, now) -> dict:
	"""Procurement plan lines on open plans (P-05A): most follow the programme,
	required on site a buffer before their task starts and requested a lead time
	before that. A line's state is the first that fits: requested, overdue (the
	pr_overdue flag the plan and a daily job keep), no date to order by, past its
	date but covered (not flagged, e.g. plant on a hire order), due within the
	window, or not yet due."""
	if "Procurement Plan" not in readable:
		return {"restricted": True}

	child = "`tabProcurement Plan Item`"
	lines = _get_list(
		"Procurement Plan",
		filters=[["Procurement Plan", "status", "not in", PLAN_CLOSED], _joined("Procurement Plan Item")],
		fields=[
			"name as plan",
			"project",
			f"{child}.item_code as item_code",
			f"{child}.task as task",
			f"{child}.procurement_route as route",
			f"{child}.anticipated_qty as qty",
			f"{child}.uom as uom",
			f"{child}.required_on_site_date as on_site",
			f"{child}.recommended_pr_date as pr_date",
			f"{child}.material_request as material_request",
			f"{child}.pr_overdue as pr_overdue",
		],
		limit_page_length=0,
	)
	horizon = getdate(add_days(now, PLAN_WINDOW_DAYS))

	def state(line):
		if line.material_request:
			return "requested"
		if line.pr_overdue:
			return "overdue"
		if not line.pr_date:
			return "no_date"
		if getdate(line.pr_date) < now:
			# Past its date and not flagged: covered another way, such as plant
			# already on a hire order (P-05A).
			return "requested"
		return "due_soon" if getdate(line.pr_date) <= horizon else "later"

	for line in lines:
		line.state = state(line)

	def plans(rows):
		return sorted({r.plan for r in rows})

	def by(key, order, labels=None):
		result = []
		for value in order:
			rows = [line for line in lines if line[key] == value]
			if rows:
				result.append({"key": value, "label": (labels or {}).get(value) or _(value or "Not set"),
				               "value": ["in", plans(rows)], "count": len(rows)})
		return result

	states = {
		"overdue": _("PR date passed"),
		"due_soon": _("PR due in {0} days").format(PLAN_WINDOW_DAYS),
		"later": _("Not yet due"),
		"no_date": _("No date to order by"),
		"requested": _("Requested or ordered"),
	}
	due = sorted((line for line in lines if line.state in ("overdue", "due_soon")), key=lambda l: getdate(l.pr_date))
	items = {}
	if due and frappe.has_permission("Item", "read"):
		items = dict(frappe.get_list("Item", filters={"name": ["in", list({l.item_code for l in due})]},
		                             fields=["name", "item_name"], as_list=True))
	statuses = _get_list("Procurement Plan", fields=["status", "count(name) as n"], group_by="status")

	return {
		"restricted": False,
		"lines": len(lines),
		"plans": len(plans(lines)),
		"from_schedule": sum(bool(line.task) for line in lines),
		"by_hand": sum(not line.task for line in lines),
		"requested": sum(line.state == "requested" for line in lines),
		"overdue": sum(line.state == "overdue" for line in lines),
		"due_soon": sum(line.state == "due_soon" for line in lines),
		"no_date": sum(line.state == "no_date" for line in lines),
		"window_days": PLAN_WINDOW_DAYS,
		"by_state": by("state", list(states), states),
		"by_route": by("route", ROUTES + (None,)),
		"by_status": _in_order(statuses, PLAN_STATUSES),
		"list": [
			{
				"plan": line.plan,
				"item": items.get(line.item_code) or line.item_code,
				"route": line.route,
				"qty": flt(line.qty),
				"uom": line.uom,
				"on_site": line.on_site,
				"pr_date": line.pr_date,
				"days": date_diff(line.pr_date, now),
				"from_schedule": bool(line.task),
			}
			for line in due[:LIST_LIMIT]
		],
	}


def _health(readable: set, now, budget: dict, plan: dict) -> list[dict]:
	"""Checks that count things needing action, so zero always means healthy.

	`critical` is kept for dates the client holds us to that have already passed.
	Milestone and deliverable dates are checked on Contracts & Awards.
	"""
	checks = []
	today_str = str(now)

	def check(label, severity, doctype, count, filters, meta=None):
		checks.append(
			{
				"label": _(label),
				"severity": severity,
				"doctype": doctype,
				"count": count,
				"filters": filters,
				"meta": meta,
			}
		)

	def names_filter(names):
		return {"name": ["in", sorted(names)]}

	award_readable = "Awarded Quotation" in readable
	active_awards = {"status": ["in", ACTIVE_STATUSES]}

	past_completion = {**active_awards, "revised_end_date": ["<", today_str]}
	check(
		"Awards past their completion date",
		"warning",
		"Awarded Quotation",
		_count("Awarded Quotation", past_completion) if award_readable else None,
		past_completion,
	)

	no_boq = None
	if award_readable and "BOQ" in readable:
		# Either link counts: a BOQ naming the award, or a component naming a BOQ.
		priced = set(_get_list("BOQ", filters={"awarded_quotation": ["is", "set"]}, pluck="awarded_quotation"))
		priced |= set(
			_get_list(
				"Awarded Quotation",
				filters=[_joined("Awarded Quotation Component"), ["Awarded Quotation Component", "boq", "is", "set"]],
				pluck="name",
				distinct=True,
			)
		)
		no_boq = set(_get_list("Awarded Quotation", filters=active_awards, pluck="name")) - priced
	check(
		"Active awards with no BOQ",
		"warning",
		"Awarded Quotation",
		len(no_boq) if no_boq is not None else None,
		names_filter(no_boq or []),
	)

	components = None
	if award_readable:
		components = _get_list(
			"Awarded Quotation",
			filters=[
				["Awarded Quotation", "status", "in", ACTIVE_STATUSES],
				_joined("Awarded Quotation Component"),
				["Awarded Quotation Component", "boq", "is", "not set"],
			],
			fields=["name"],
			limit_page_length=0,
		)
	check(
		"Award components with no BOQ linked",
		"warning",
		"Awarded Quotation",
		len(components) if components is not None else None,
		names_filter({c.name for c in components or []}),
	)

	unallocated = None if budget.get("restricted") else budget.get("unallocated_lines")
	check(
		"Approved BOQ lines not yet allocated to a WBS",
		"warning",
		"BOQ",
		unallocated,
		names_filter(budget.get("unallocated_boqs") or []),
	)

	pending_boq = {"status": "Pending Approval"}
	check(
		"BOQs waiting for approval",
		"warning",
		"BOQ",
		_count("BOQ", pending_boq) if "BOQ" in readable else None,
		pending_boq,
	)

	with_client = {"status": "Submitted to Client"}
	check(
		"Variation orders waiting on the client",
		"warning",
		"Variation Order",
		_count("Variation Order", with_client) if "Variation Order" in readable else None,
		with_client,
	)

	# A plan line is late when its PR date has passed with nothing requested or
	# ordered: the line's pr_overdue flag (P-05A), kept by the plan and a daily job.
	late_lines = None
	if "Procurement Plan" in readable:
		late_lines = _get_list(
			"Procurement Plan",
			filters=[
				["Procurement Plan", "status", "not in", ["Cancelled", "Completed"]],
				["Procurement Plan Item", "pr_overdue", "=", 1],
			],
			fields=["name", "project", "`tabProcurement Plan Item`.item_code as item_code"],
			limit_page_length=0,
		)
	check(
		"Plan lines past their PR date with nothing requested",
		"warning",
		"Procurement Plan",
		len(late_lines) if late_lines is not None else None,
		names_filter({line.name for line in late_lines or []}),
	)

	# A line with no required date has nothing to work back from, so it can never
	# be flagged late: usually a task with no start date, or a line typed in by
	# hand without one.
	undated = None
	if not plan.get("restricted"):
		undated = next((row for row in plan["by_state"] if row["key"] == "no_date"), None)
	check(
		"Plan lines with no date to order by",
		"warning",
		"Procurement Plan",
		(undated or {}).get("count", 0) if not plan.get("restricted") else None,
		{"name": undated["value"]} if undated else names_filter([]),
	)

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))


# ---------------------------------------------------------------- company scope
# Awards carry a company; BOQs, allocations and plans carry a project; variation
# orders and deliverables hang off an award. Each is narrowed to the default
# company through whichever of those it has.


def _scope_filters(doctype: str) -> list:
	company = default_company()
	if not company:
		return []
	if doctype == "Awarded Quotation":
		return [[doctype, "company", "=", company]]
	if doctype in ("BOQ", "WBS Allocation", "Procurement Plan"):
		return [[doctype, "project", "in", company_projects(company) or [""]]]
	if doctype in ("Variation Order", "Deliverable"):
		awards = frappe.get_all("Awarded Quotation", filters={"company": company}, pluck="name")
		return [[doctype, "awarded_quotation", "in", awards or [""]]]
	return []


_unscoped_get_list = frappe.get_list


def _get_list(doctype, *args, filters=None, **kwargs):
	"""frappe.get_list, narrowed to the default company for this module's doctypes."""
	extra = _scope_filters(doctype)
	if extra:
		if isinstance(filters, dict):
			filters = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
		filters = list(filters or []) + extra
	return _unscoped_get_list(doctype, *args, filters=filters, **kwargs)
