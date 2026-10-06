# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Inventory Movement Overview" tab of the Inventory Movement workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency.

Stock on hand is read from Bin, which carries no company: it is scoped through
the company's warehouses, and a warehouse's Warehouse Type says where the stock
sits ("Transit" on a barge or truck, "Site" in a site store, anything else in a
store). Movements are Stock Entries, told apart the way the workspace reports
tell them apart: a dispatch is one with `add_to_transit` set (Stock Sent to
Transit), and an issue to the works is one whose purpose is Material Issue, the
same rule the Material Issue Register and the consumption reports use. Cost
code and WBS live on the entry's lines (Stock Entry Detail).
"""

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, now_datetime, today

from a3_constructa.api.utils import company_projects, default_company, default_currency

# Workspace report filters, reused so the counts here match the reports.
DISPATCH = {"docstatus": 1, "add_to_transit": 1}
ISSUE = {"docstatus": 1, "purpose": "Material Issue"}
SITE_RETURN = "Site Material Return"
SITE_REQUEST = {"docstatus": 1, "material_request_type": "Material Transfer"}
# A Material Transfer request is "Transferred" once everything has gone out.
REQUEST_OPEN = ("Pending", "Partially Received")

# Stock still on the way: dispatched, not all of it received at the other end.
OPEN_DISPATCH = {**DISPATCH, "per_transferred": ["<", 100]}

# In the order goods travel: out of a store, through transit, into a site store.
WAREHOUSE_KINDS = (("store", "Stores"), ("transit", "In transit"), ("site", "Site stores"))
TRANSPORT_MODES = ("Barge", "Truck", "Rail", "Air")

RECENT_DAYS = 30
PERIOD_DAYS = 90
TRANSIT_DAYS = 7
IDLE_DAYS = 90
DRAFT_DAYS = 3
LATEST = 8
TOP_ROWS = 5


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {
		dt
		for dt in ("Stock Entry", "Bin", "Material Request", "Stock Ledger Entry")
		if frappe.has_permission(dt, "read")
	}
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"stock": _stock(readable),
		"transit": _transit(readable, now),
		"issues": _issues(readable, now),
		"movements": _movements(readable, now),
		"requests": _requests(readable, now),
		"health": _health(readable, now),
	}


def _warehouses() -> list[dict]:
	"""The default company's stock warehouses (not groups), with their type.

	Read like company_projects: this only decides which Bin rows belong to the
	company, and every figure is still read through get_list.
	"""
	company = default_company()
	if not company:
		return []
	return frappe.get_all(
		"Warehouse",
		filters={"company": company, "is_group": 0},
		fields=["name", "warehouse_type"],
		order_by="lft",
	)


def _scoped(doctype, filters=None):
	"""`filters` narrowed to the default company, as a list of conditions."""
	if isinstance(filters, dict):
		conditions = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
	else:
		conditions = list(filters or [])
	company = default_company()
	if company:
		meta = frappe.get_meta(doctype)
		if meta.has_field("company"):
			conditions.append([doctype, "company", "=", company])
		elif meta.has_field("project"):
			conditions.append([doctype, "project", "in", company_projects(company) or [""]])
		elif meta.has_field("warehouse"):
			conditions.append([doctype, "warehouse", "in", [w.name for w in _warehouses()] or [""]])
	return conditions


def _bin_filters(filters=None) -> dict:
	"""Bin list filters that hold the company scope themselves, for links."""
	out = dict(filters or {})
	if default_company():
		out["warehouse"] = ["in", [w.name for w in _warehouses()] or [""]]
	return out


def _count(doctype, filters=None) -> int:
	return frappe.get_list(doctype, filters=_scoped(doctype, filters), fields=["count(name) as n"])[0].n


def _top(rows, limit, measure="count") -> list[dict]:
	"""The largest `limit` groups, the rest folded into one "Other" row."""
	rows = sorted(rows, key=lambda row: -flt(row[measure]))
	top = rows[:limit]
	rest = rows[limit:]
	if rest:
		top.append(
			{
				"label": _("Other"),
				"value": None,
				"count": sum(row["count"] for row in rest),
				"amount": sum(flt(row.get("amount")) for row in rest),
				"other": True,
			}
		)
	return top


def _short(warehouse) -> str:
	"""A warehouse without its " - ABBR" company suffix."""
	company = default_company()
	abbr = company and frappe.get_cached_value("Company", company, "abbr")
	suffix = f" - {abbr}" if abbr else None
	return warehouse[: -len(suffix)] if suffix and warehouse and warehouse.endswith(suffix) else warehouse


def _titles(doctype, field, names) -> dict:
	"""Display names for link values, where the caller may read the master."""
	names = [name for name in names if name]
	if not names or not frappe.has_permission(doctype, "read"):
		return {}
	return {
		row.name: row[field]
		for row in frappe.get_list(doctype, filters={"name": ["in", names]}, fields=["name", field])
		if row[field]
	}


def _since(now, days) -> str:
	return str(add_days(now, -days))


# ---------------------------------------------------------------- sections


def _stock(readable) -> dict:
	if "Bin" not in readable:
		return {"restricted": True}

	held = {"actual_qty": ["!=", 0]}
	kind_of = {
		w.name: "transit" if w.warehouse_type == "Transit" else "site" if w.warehouse_type == "Site" else "store"
		for w in _warehouses()
	}

	by_warehouse = frappe.get_list(
		"Bin",
		filters=_scoped("Bin", held),
		fields=["warehouse", "sum(stock_value) as amount", "count(name) as n", "max(actual_qty) as most"],
		group_by="warehouse",
	)
	by_item = frappe.get_list(
		"Bin",
		filters=_scoped("Bin", held),
		fields=["item_code", "sum(stock_value) as amount", "count(name) as n", "max(actual_qty) as most"],
		group_by="item_code",
	)

	kinds = []
	for key, label in WAREHOUSE_KINDS:
		names = [row.warehouse for row in by_warehouse if kind_of.get(row.warehouse, "store") == key]
		kinds.append(
			{
				"key": key,
				"label": _(label),
				"amount": sum(flt(row.amount) for row in by_warehouse if row.warehouse in names),
				# Already the company's warehouses, so no _bin_filters here.
				"filters": {**held, "warehouse": ["in", names or [""]]},
			}
		)

	item_names = _titles("Item", "item_name", [row.item_code for row in by_item])
	warehouses = [
		{"label": _short(row.warehouse), "value": row.warehouse, "count": row.n, "amount": flt(row.amount)}
		for row in by_warehouse
	]
	items = [
		{
			"label": item_names.get(row.item_code) or row.item_code,
			"value": row.item_code,
			"count": row.n,
			"amount": flt(row.amount),
		}
		for row in by_item
	]

	return {
		"restricted": False,
		"filters": _bin_filters(held),
		"value": flt(sum(row["amount"] for row in warehouses), 2),
		"items": sum(1 for row in by_item if flt(row.most) > 0),
		"warehouses": sum(1 for row in by_warehouse if flt(row.most) > 0),
		"negative": _count("Bin", {"actual_qty": ["<", 0]}),
		"kinds": kinds,
		"by_warehouse": _top(warehouses, TOP_ROWS, measure="amount"),
		"warehouse_total": flt(sum(row["amount"] for row in warehouses), 2),
		"by_item": _top(items, TOP_ROWS, measure="amount"),
		"item_total": flt(sum(row["amount"] for row in items), 2),
	}


def _transit(readable, now) -> dict:
	if "Stock Entry" not in readable:
		return {"restricted": True}

	open_row = frappe.get_list(
		"Stock Entry",
		filters=_scoped("Stock Entry", OPEN_DISPATCH),
		fields=["count(name) as n", "min(posting_date) as oldest"],
	)[0]

	period = {**DISPATCH, "posting_date": [">=", _since(now, PERIOD_DAYS)]}
	found = {
		row.mode or None: row
		for row in frappe.get_list(
			"Stock Entry",
			filters=_scoped("Stock Entry", period),
			fields=["mode_of_transport as mode", "count(name) as n", "sum(total_amount) as amount"],
			group_by="mode_of_transport",
		)
	}
	# A blank select and a null one are both "not set".
	not_set = [row for mode, row in found.items() if mode not in TRANSPORT_MODES]
	by_mode = [
		{"label": _(mode), "value": mode, "count": found[mode].n, "amount": flt(found[mode].amount)}
		for mode in TRANSPORT_MODES
		if mode in found
	]
	if not_set:
		by_mode.append(
			{
				"label": _("Not set"),
				"value": None,
				"count": sum(row.n for row in not_set),
				"amount": sum(flt(row.amount) for row in not_set),
			}
		)

	return {
		"restricted": False,
		"filters": OPEN_DISPATCH,
		"count": open_row.n,
		"oldest_days": date_diff(now, open_row.oldest) if open_row.oldest else None,
		"mode_filters": period,
		"by_mode": by_mode,
		"mode_total": sum(row["count"] for row in by_mode),
	}


def _issues(readable, now) -> dict:
	if "Stock Entry" not in readable:
		return {"restricted": True}

	recent = {"posting_date": [">=", _since(now, RECENT_DAYS)]}
	month = frappe.get_list(
		"Stock Entry",
		filters=_scoped("Stock Entry", {**ISSUE, **recent}),
		fields=["count(name) as n", "sum(total_outgoing_value) as amount"],
	)[0]

	period = {**ISSUE, "posting_date": [">=", _since(now, PERIOD_DAYS)]}
	lines = frappe.get_list(
		"Stock Entry",
		filters=_scoped("Stock Entry", period),
		fields=[
			"name",
			"`tabStock Entry Detail`.wbs as wbs",
			"`tabStock Entry Detail`.cost_code as cost_code",
			"`tabStock Entry Detail`.amount as amount",
		],
		limit_page_length=0,
	)

	def by(field, titles_doctype, title_field):
		entries, amounts = defaultdict(set), defaultdict(float)
		for line in lines:
			key = line[field] or None
			entries[key].add(line.name)
			amounts[key] += flt(line.amount)
		titles = _titles(titles_doctype, title_field, list(entries))
		rows = [
			{
				"label": (titles.get(key) or key) if key else _("Not set"),
				"value": key,
				"count": len(entries[key]),
				"amount": flt(amounts[key], 2),
			}
			for key in entries
		]
		return _top(rows, TOP_ROWS, measure="amount"), flt(sum(amounts.values()), 2)

	by_wbs, wbs_total = by("wbs", "WBS", "wbs_name")
	by_cost_code, cost_code_total = by("cost_code", "Cost Code", "description")

	return {
		"restricted": False,
		"value_30d": flt(month.amount),
		"count_30d": month.n,
		"returns_30d": _count("Stock Entry", {"docstatus": 1, "stock_entry_type": SITE_RETURN, **recent}),
		"filters": period,
		"by_wbs": by_wbs,
		"wbs_total": wbs_total,
		"by_cost_code": by_cost_code,
		"cost_code_total": cost_code_total,
	}


def _movements(readable, now) -> dict:
	if "Stock Entry" not in readable:
		return {"restricted": True}

	period = {"docstatus": 1, "posting_date": [">=", _since(now, PERIOD_DAYS)]}
	by_type = [
		{"label": _(row.stock_entry_type) if row.stock_entry_type else _("Not set"), "value": row.stock_entry_type,
		 "count": row.n, "amount": flt(row.amount)}
		for row in frappe.get_list(
			"Stock Entry",
			filters=_scoped("Stock Entry", period),
			fields=["stock_entry_type", "count(name) as n", "sum(total_amount) as amount"],
			group_by="stock_entry_type",
		)
	]

	latest = frappe.get_list(
		"Stock Entry",
		filters=_scoped("Stock Entry", {"docstatus": ["<", 2]}),
		fields=["name", "stock_entry_type", "posting_date", "docstatus", "total_amount", "add_to_transit"],
		order_by="posting_date desc, posting_time desc, creation desc",
		limit_page_length=LATEST,
	)
	# Where each entry took its goods from and to, read off its lines.
	ends = defaultdict(lambda: {"from": [], "to": []})
	if latest:
		for line in frappe.get_list(
			"Stock Entry",
			filters={"name": ["in", [row.name for row in latest]]},
			fields=[
				"name",
				"`tabStock Entry Detail`.s_warehouse as s",
				"`tabStock Entry Detail`.t_warehouse as t",
				"`tabStock Entry Detail`.idx as idx",
			],
			order_by="`tabStock Entry Detail`.idx asc",
			limit_page_length=0,
		):
			for side, warehouse in (("from", line.s), ("to", line.t)):
				if warehouse and _short(warehouse) not in ends[line.name][side]:
					ends[line.name][side].append(_short(warehouse))

	return {
		"restricted": False,
		"filters": period,
		"by_type": _top(by_type, TOP_ROWS, measure="amount"),
		"type_total": flt(sum(row["amount"] for row in by_type), 2),
		"latest": [
			{
				"name": row.name,
				"type": row.stock_entry_type,
				"date": row.posting_date,
				"draft": row.docstatus == 0,
				"amount": flt(row.total_amount),
				"from": ends[row.name]["from"],
				"to": ends[row.name]["to"],
			}
			for row in latest
		],
	}


def _requests(readable, now) -> dict:
	if "Material Request" not in readable:
		return {"restricted": True}
	waiting = {**SITE_REQUEST, "status": ["in", list(REQUEST_OPEN)]}
	return {
		"restricted": False,
		"filters": waiting,
		"open": _count("Material Request", waiting),
		"overdue": _count("Material Request", {**waiting, "schedule_date": ["<", str(now)]}),
	}


def _health(readable, now) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for stock the books cannot account for: goods still out in
	transit past their time, and balances below zero.
	"""
	checks = []
	se = "Stock Entry" in readable
	bins = "Bin" in readable

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append(
			{"label": label, "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta}
		)

	late = {**OPEN_DISPATCH, "posting_date": ["<", _since(now, TRANSIT_DAYS)]}
	check(
		_("Dispatches still in transit after {0} days").format(TRANSIT_DAYS),
		"critical",
		"Stock Entry",
		_count("Stock Entry", late) if se else None,
		late,
		meta=_("Not fully received at the other end"),
	)

	below = {"actual_qty": ["<", 0]}
	check(
		_("Stock balances below zero"),
		"critical",
		"Bin",
		_count("Bin", below) if bins else None,
		_bin_filters(below),
		meta=_("Item stock per warehouse"),
	)

	overdue = None
	if "Material Request" in readable:
		overdue = {**SITE_REQUEST, "status": ["in", list(REQUEST_OPEN)], "schedule_date": ["<", str(now)]}
	check(
		_("Site requests past their required date"),
		"warning",
		"Material Request",
		_count("Material Request", overdue) if overdue else None,
		overdue,
	)

	uncoded = None
	if se:
		uncoded = sorted(
			set(
				frappe.get_list(
					"Stock Entry",
					filters=_scoped(
						"Stock Entry",
						[
							["Stock Entry", "docstatus", "<", 2],
							["Stock Entry", "purpose", "=", "Material Issue"],
							["Stock Entry", "posting_date", ">=", _since(now, PERIOD_DAYS)],
							["Stock Entry Detail", "cost_code", "is", "not set"],
						],
					),
					pluck="name",
					limit_page_length=0,
				)
			)
		)
	check(
		_("Material issues in the last {0} days missing a cost code").format(PERIOD_DAYS),
		"warning",
		"Stock Entry",
		len(uncoded) if uncoded is not None else None,
		{"name": ["in", uncoded or []]},
	)

	idle = None
	if bins and "Stock Ledger Entry" in readable:
		last_moved = {
			(row.item_code, row.warehouse): row.last
			for row in frappe.get_list(
				"Stock Ledger Entry",
				filters=_scoped("Stock Ledger Entry", {"is_cancelled": 0}),
				fields=["item_code", "warehouse", "max(posting_date) as last"],
				group_by="item_code, warehouse",
				limit_page_length=0,
			)
		}
		cutoff = getdate(add_days(now, -IDLE_DAYS))
		idle = sorted(
			row.name
			for row in frappe.get_list(
				"Bin",
				filters=_scoped("Bin", {"actual_qty": [">", 0]}),
				fields=["name", "item_code", "warehouse"],
				limit_page_length=0,
			)
			if last_moved.get((row.item_code, row.warehouse))
			and getdate(last_moved[(row.item_code, row.warehouse)]) < cutoff
		)
	check(
		_("Stock lines not moved in {0} days").format(IDLE_DAYS),
		"warning",
		"Bin",
		len(idle) if idle is not None else None,
		{"name": ["in", idle or []]},
		meta=_("Slow-moving stock"),
	)

	drafts = {"docstatus": 0, "posting_date": ["<", _since(now, DRAFT_DAYS)]}
	check(
		_("Stock entries left in draft over {0} days").format(DRAFT_DAYS),
		"warning",
		"Stock Entry",
		_count("Stock Entry", drafts) if se else None,
		drafts,
		meta=_("Not yet posted to stock"),
	)

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
