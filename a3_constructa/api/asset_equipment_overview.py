# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Asset & Equipment Overview" tab of the Asset & Equipment workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency.

The register is every submitted Asset not sold, scrapped or capitalised, which
is the Fixed Asset Register's "In Location". Statuses keep ERPNext's names, so
"Out of Order" counts exactly what the workspace's Assets Out of Order report
lists. Book value is ERPNext's own: the finance
book row's value after depreciation when the asset depreciates, the asset's
otherwise.

Small tools are serialised stock, not Assets. A Tool Issue hands them to an
employee, and a line is out until it is marked returned, read the way the Tools
Outstanding report reads it. Tool Issues and maintenance logs carry no company,
so they are scoped through the issuing warehouse and the maintenance plan.
"""

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, now_datetime, today

from a3_constructa.api.utils import company_projects, default_company, default_currency

DOCTYPES = (
	"Asset",
	"Asset Depreciation Schedule",
	"Asset Repair",
	"Asset Maintenance Log",
	"Asset Spare Part",
	"Tool Issue",
	"Bin",
)

OFF_REGISTER = ("Sold", "Scrapped", "Capitalized")
ON_REGISTER = {"docstatus": 1, "status": ["not in", list(OFF_REGISTER)]}
ASSET_STATUSES = (
	"Submitted",
	"Partially Depreciated",
	"Fully Depreciated",
	"In Maintenance",
	"Out of Order",
	"Issue",
	"Receipt",
)

MAINTENANCE_OPEN = {"docstatus": ["<", 2], "maintenance_status": ["in", ["Planned", "Overdue"]]}
REPAIR_OPEN = {"docstatus": ["<", 2], "repair_status": "Pending"}

MAINTENANCE_AHEAD_DAYS = 30
REPAIR_WAIT_DAYS = 7
# The depreciation chart: this many months booked, then as many scheduled
# starting with the current one.
TREND_HALF = 6
COMING_UP = 8
TOP_ROWS = 5


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {dt for dt in DOCTYPES if frappe.has_permission(dt, "read")}
	# Read once, used by several sections.
	assets = _assets(readable)
	tools = _tool_lines(readable, now)
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"register": _register(assets),
		"tools": _tools(tools),
		"depreciation": _depreciation(readable, assets, now),
		"repairs": _repairs(readable, now),
		"maintenance": _maintenance(readable, now),
		"coming_up": _coming_up(readable, assets, tools, now),
		"health": _health(readable, assets, tools, now),
	}


# ---------------------------------------------------------------- company scope


def _scope(doctype) -> list:
	"""The conditions that narrow `doctype` to the default company."""
	company = default_company()
	if not company:
		return []
	if doctype == "Asset Maintenance Log":
		plans = frappe.get_all("Asset Maintenance", filters={"company": company}, pluck="name")
		return [[doctype, "asset_maintenance", "in", plans or [""]]]
	if doctype == "Tool Issue":
		# The project is optional on an issue; the store it left from is not.
		return [[doctype, "from_warehouse", "in", _warehouses() or [""]]]
	meta = frappe.get_meta(doctype)
	if meta.has_field("company"):
		return [[doctype, "company", "=", company]]
	if meta.has_field("project"):
		return [[doctype, "project", "in", company_projects(company) or [""]]]
	return []


def _warehouses() -> list[str]:
	company = default_company()
	return frappe.get_all("Warehouse", filters={"company": company} if company else {}, pluck="name")


def _scoped(doctype, filters=None) -> list:
	"""`filters` narrowed to the default company, as a list of conditions."""
	if isinstance(filters, dict):
		conditions = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
	else:
		conditions = list(filters or [])
	return conditions + _scope(doctype)


def _list_filters(doctype, filters) -> dict:
	"""`filters` plus the company scope, as list-view filters, so a clicked row
	opens exactly the records that were counted."""
	scoped = dict(filters)
	for _dt, field, operator, value in _scope(doctype):
		scoped[field] = value if operator == "=" else [operator, value]
	return scoped


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


def _group(rows, field, labels=None, empty_label=None, amount="book_value") -> list[dict]:
	"""Rows counted and summed by `field`; an empty value is its own row."""
	groups = {}
	for row in rows:
		key = row.get(field) or None
		group = groups.setdefault(
			key,
			{
				"label": (labels or {}).get(key) or key or empty_label or _("Not set"),
				"value": key,
				"count": 0,
				"amount": 0.0,
			},
		)
		group["count"] += 1
		group["amount"] += flt(row.get(amount))
	return list(groups.values())


def _project_titles(names) -> dict:
	names = [name for name in names if name]
	if not names or not frappe.has_permission("Project", "read"):
		return {}
	return {
		row.name: row.project_name
		for row in frappe.get_list("Project", filters={"name": ["in", names]}, fields=["name", "project_name"])
	}


def _employee_names(names) -> dict:
	names = [name for name in names if name]
	if not names or not frappe.has_permission("Employee", "read"):
		return {}
	return {
		row.name: row.employee_name
		for row in frappe.get_list("Employee", filters={"name": ["in", names]}, fields=["name", "employee_name"])
	}


def _finance_book() -> str | None:
	company = default_company()
	return (frappe.get_cached_value("Company", company, "default_finance_book") if company else None) or None


# ---------------------------------------------------------------- shared reads


def _assets(readable) -> list | None:
	"""The register, one row per asset with its book value; None without access."""
	if "Asset" not in readable:
		return None
	rows = frappe.get_list(
		"Asset",
		filters=_scoped("Asset", ON_REGISTER),
		fields=[
			"name",
			"asset_name",
			"status",
			"asset_category",
			"location",
			"project",
			"gross_purchase_amount",
			"value_after_depreciation",
			"calculate_depreciation",
			"warranty_expiry_date",
			"insurance_end_date",
			"`tabAsset Finance Book`.finance_book as book",
			"`tabAsset Finance Book`.idx as book_idx",
			"`tabAsset Finance Book`.value_after_depreciation as book_value_after",
		],
		order_by="`tabAsset`.name asc",
		limit_page_length=0,
	)
	finance_book = _finance_book()
	assets, books = {}, defaultdict(list)
	for row in rows:
		assets.setdefault(row.name, row)
		if row.book_idx:
			books[row.name].append(row)
	for name, asset in assets.items():
		asset.book_value = _book_value(asset, books[name], finance_book)
	return list(assets.values())


def _book_value(asset, books, finance_book) -> float:
	"""ERPNext's value after depreciation: a depreciating asset keeps it on its
	finance book row, the company's default book or else the first."""
	if not asset.calculate_depreciation or not books:
		return flt(asset.value_after_depreciation)
	row = next((b for b in books if (b.book or None) == finance_book), None) or min(books, key=lambda b: b.book_idx)
	return flt(row.book_value_after)


def _tool_lines(readable, now) -> list | None:
	"""Tool lines still out, as the Tools Outstanding report lists them."""
	if "Tool Issue" not in readable:
		return None
	rows = frappe.get_list(
		"Tool Issue",
		filters=_scoped(
			"Tool Issue",
			[["Tool Issue", "docstatus", "=", 1], ["Tool Issue Item", "is_returned", "=", 0]],
		),
		fields=[
			"name",
			"issued_to",
			"project",
			"expected_return_date",
			"`tabTool Issue Item`.qty as qty",
			"`tabTool Issue Item`.returned_qty as returned_qty",
			"`tabTool Issue Item`.valuation_rate as rate",
			"`tabTool Issue Item`.expected_return_date as line_due",
		],
		limit_page_length=0,
	)
	for row in rows:
		row.out = flt(row.qty) - flt(row.returned_qty)
		row.value = row.out * flt(row.rate)
		row.due = row.line_due or row.expected_return_date
		row.late = bool(row.due and getdate(row.due) < now)
	return rows


# ---------------------------------------------------------------- sections


def _register(assets) -> dict:
	if assets is None:
		return {"restricted": True}

	statuses = Counter(asset.status for asset in assets)
	order = [s for s in ASSET_STATUSES if statuses.get(s)] + sorted(s for s in statuses if s not in ASSET_STATUSES)
	by_status = {row["value"]: row for row in _group(assets, "status")}
	projects = _project_titles({asset.project for asset in assets})

	return {
		"restricted": False,
		"filters": _list_filters("Asset", ON_REGISTER),
		"count": len(assets),
		"cost": sum(flt(asset.gross_purchase_amount) for asset in assets),
		"book_value": sum(asset.book_value for asset in assets),
		"out_of_order": statuses.get("Out of Order", 0),
		"in_maintenance": statuses.get("In Maintenance", 0),
		"by_status": [{**by_status[s], "label": _(s)} for s in order],
		"by_category": _top(_group(assets, "asset_category"), TOP_ROWS, measure="amount"),
		"by_location": _top(_group(assets, "location"), TOP_ROWS),
		"by_project": _top(_group(assets, "project", projects, _("No project")), TOP_ROWS),
	}


def _tools(lines) -> dict:
	if lines is None:
		return {"restricted": True}

	# One row per issue, so a breakdown row opens as many issues as it counts.
	issues = {}
	for line in lines:
		issue = issues.setdefault(line.name, {"project": line.project, "value": 0.0})
		issue["value"] += line.value
	projects = _project_titles({issue["project"] for issue in issues.values()})

	return {
		"restricted": False,
		"filters": {"name": ["in", sorted(issues)]},
		"qty": sum(line.out for line in lines),
		"value": sum(line.value for line in lines),
		"people": len({line.issued_to for line in lines}),
		"issues": len(issues),
		"late": len({line.name for line in lines if line.late}),
		"by_project": _top(
			_group(issues.values(), "project", projects, _("No project"), amount="value"), TOP_ROWS
		),
	}


def _depreciation(readable, assets, now) -> dict:
	if "Asset Depreciation Schedule" not in readable:
		return {"restricted": True}

	first = getdate(add_months(get_first_day(now), -TREND_HALF))
	last = getdate(get_last_day(add_months(now, TREND_HALF - 1)))
	year_ago = getdate(add_months(now, -12))
	finance_book = _finance_book()
	rows = frappe.get_list(
		"Asset Depreciation Schedule",
		filters=_scoped(
			"Asset Depreciation Schedule",
			[
				["Asset Depreciation Schedule", "docstatus", "=", 1],
				["Asset Depreciation Schedule", "status", "=", "Active"],
				["Asset Depreciation Schedule", "finance_book", *(["=", finance_book] if finance_book else ["is", "not set"])],
				["Depreciation Schedule", "schedule_date", "between", [str(min(first, year_ago)), str(last)]],
			],
		),
		fields=[
			"asset",
			"`tabDepreciation Schedule`.schedule_date as date",
			"`tabDepreciation Schedule`.depreciation_amount as amount",
			"`tabDepreciation Schedule`.journal_entry as journal_entry",
		],
		limit_page_length=0,
	)
	on_register = None if assets is None else {asset.name for asset in assets}
	booked = [row for row in rows if row.journal_entry]
	# What is still to come only counts for assets still on the register.
	planned = [row for row in rows if not row.journal_entry and (on_register is None or row.asset in on_register)]

	ahead = [row for row in planned if getdate(row.date) >= now]
	next_date = min((getdate(row.date) for row in ahead), default=None)

	months = [getdate(add_months(first, i)) for i in range(TREND_HALF * 2)]
	sums = {m.strftime("%Y-%m"): {"booked": 0.0, "scheduled": 0.0} for m in months}
	for kind, part in (("booked", booked), ("scheduled", planned)):
		for row in part:
			key = getdate(row.date).strftime("%Y-%m")
			if key in sums:
				sums[key][kind] += flt(row.amount)

	return {
		"restricted": False,
		"booked_year": sum(flt(row.amount) for row in booked if year_ago < getdate(row.date) <= now),
		"next_date": next_date,
		"next_amount": sum(flt(row.amount) for row in ahead if getdate(row.date) == next_date),
		"trend": [
			{
				"month": m.strftime("%Y-%m"),
				"label": m.strftime("%b %Y"),
				"short": m.strftime("%b"),
				"booked": sums[m.strftime("%Y-%m")]["booked"],
				"scheduled": sums[m.strftime("%Y-%m")]["scheduled"],
			}
			for m in months
		],
	}


def _repairs(readable, now) -> dict:
	if "Asset Repair" not in readable:
		return {"restricted": True}

	year = {"docstatus": ["<", 2], "failure_date": [">=", str(add_months(now, -12))]}
	rows = frappe.get_list(
		"Asset Repair",
		filters=_scoped("Asset Repair", year),
		fields=["name", "asset", "asset_name", "repair_cost", "total_repair_cost"],
		limit_page_length=0,
	)
	for row in rows:
		# As the Asset Maintenance Cost report adds it up: the repair charge plus
		# the spares, which total_repair_cost already includes.
		row.cost = flt(row.repair_cost) + max(flt(row.total_repair_cost) - flt(row.repair_cost), 0)
	names = {row.asset: row.asset_name for row in rows}

	return {
		"restricted": False,
		"filters": _list_filters("Asset Repair", year),
		"count": len(rows),
		"cost": sum(row.cost for row in rows),
		"open": _count("Asset Repair", REPAIR_OPEN),
		"by_asset": _top(_group(rows, "asset", names, amount="cost"), TOP_ROWS, measure="amount"),
	}


def _maintenance(readable, now) -> dict:
	if "Asset Maintenance Log" not in readable:
		return {"restricted": True}
	soon = str(add_days(now, MAINTENANCE_AHEAD_DAYS))
	return {
		"restricted": False,
		"open": _count("Asset Maintenance Log", MAINTENANCE_OPEN),
		"due_soon": _count("Asset Maintenance Log", {**MAINTENANCE_OPEN, "due_date": ["between", [str(now), soon]]}),
		"overdue": _count("Asset Maintenance Log", {**MAINTENANCE_OPEN, "due_date": ["<", str(now)]}),
	}


def _coming_up(readable, assets, tools, now) -> dict:
	"""Dated things to act on, soonest first: maintenance due, tools due back,
	warranties and insurance ending. Overdue ones lead, flagged late."""
	if not readable & {"Asset", "Asset Maintenance Log", "Tool Issue"}:
		return {"restricted": True}
	rows = []

	if "Asset Maintenance Log" in readable:
		for log in frappe.get_list(
			"Asset Maintenance Log",
			filters=_scoped("Asset Maintenance Log", {**MAINTENANCE_OPEN, "due_date": ["is", "set"]}),
			fields=["name", "asset_name", "item_name", "task_name", "due_date"],
			order_by="due_date asc",
			limit_page_length=COMING_UP,
		):
			rows.append(
				{
					"kind": "maintenance",
					"doctype": "Asset Maintenance Log",
					"name": log.name,
					"title": log.item_name or log.asset_name,
					"detail": log.task_name,
					"date": log.due_date,
				}
			)

	if tools:
		due = {}
		for line in tools:
			issue = due.setdefault(line.name, {"issued_to": line.issued_to, "date": None, "qty": 0.0})
			issue["qty"] += line.out
			if line.due and (issue["date"] is None or getdate(line.due) < issue["date"]):
				issue["date"] = getdate(line.due)
		people = _employee_names({issue["issued_to"] for issue in due.values()})
		for name, issue in due.items():
			if issue["date"]:
				rows.append(
					{
						"kind": "tool_return",
						"doctype": "Tool Issue",
						"name": name,
						"title": people.get(issue["issued_to"]) or issue["issued_to"],
						"qty": issue["qty"],
						"date": issue["date"],
					}
				)

	for asset in assets or []:
		for kind, field in (("warranty", "warranty_expiry_date"), ("insurance", "insurance_end_date")):
			if asset.get(field) and getdate(asset[field]) >= now:
				rows.append(
					{
						"kind": kind,
						"doctype": "Asset",
						"name": asset.name,
						"title": asset.asset_name or asset.name,
						"date": asset[field],
					}
				)

	for row in rows:
		row["date"] = getdate(row["date"])
		row["late"] = row["date"] < now
	rows.sort(key=lambda row: (row["date"], row["name"]))
	return {"restricted": False, "rows": rows[:COMING_UP]}


def _health(readable, assets, tools, now) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for dates already missed.
	"""
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append(
			{"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta}
		)

	overdue = {**MAINTENANCE_OPEN, "due_date": ["<", str(now)]}
	check(
		"Maintenance past its due date",
		"critical",
		"Asset Maintenance Log",
		_count("Asset Maintenance Log", overdue) if "Asset Maintenance Log" in readable else None,
		_list_filters("Asset Maintenance Log", overdue),
	)

	late_issues = None if tools is None else sorted({line.name for line in tools if line.late})
	check(
		"Tool issues past their return date",
		"critical",
		"Tool Issue",
		len(late_issues) if late_issues is not None else None,
		{"name": ["in", late_issues or []]},
	)

	out_of_order = {"status": "Out of Order"}
	check(
		"Assets out of order",
		"warning",
		"Asset",
		sum(1 for asset in assets if asset.status == "Out of Order") if assets is not None else None,
		_list_filters("Asset", out_of_order),
	)

	stalled = {**REPAIR_OPEN, "failure_date": ["<", str(add_days(now, -REPAIR_WAIT_DAYS))]}
	check(
		f"Repairs still open after {REPAIR_WAIT_DAYS} days",
		"warning",
		"Asset Repair",
		_count("Asset Repair", stalled) if "Asset Repair" in readable else None,
		_list_filters("Asset Repair", stalled),
	)

	unbooked = _unbooked_depreciation(readable, assets, now)
	check(
		"Depreciation due but not booked",
		"warning",
		"Asset",
		len(unbooked) if unbooked is not None else None,
		{"name": ["in", unbooked or []]},
		meta=_("A scheduled date has passed with no journal entry"),
	)

	short = _spares_short(readable)
	check(
		"Spare parts below minimum stock",
		"warning",
		"Asset Spare Part",
		len(short) if short is not None else None,
		{"name": ["in", short or []]},
		meta=_("Minimum set on the spare part, stock in its warehouse"),
	)

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))


def _unbooked_depreciation(readable, assets, now) -> list | None:
	if assets is None or "Asset Depreciation Schedule" not in readable:
		return None
	on_register = {asset.name for asset in assets}
	finance_book = _finance_book()
	due = frappe.get_list(
		"Asset Depreciation Schedule",
		filters=_scoped(
			"Asset Depreciation Schedule",
			[
				["Asset Depreciation Schedule", "docstatus", "=", 1],
				["Asset Depreciation Schedule", "status", "=", "Active"],
				["Asset Depreciation Schedule", "finance_book", *(["=", finance_book] if finance_book else ["is", "not set"])],
				["Depreciation Schedule", "schedule_date", "<", str(now)],
				["Depreciation Schedule", "journal_entry", "is", "not set"],
			],
		),
		pluck="asset",
		limit_page_length=0,
	)
	return sorted({name for name in due if name in on_register})


def _spares_short(readable) -> list | None:
	"""Spare parts holding less than their minimum: in their default warehouse,
	or across the company's warehouses when none is set."""
	if not {"Asset Spare Part", "Bin"} <= readable:
		return None
	warehouses = set(_warehouses())
	parts = [
		part
		for part in frappe.get_list(
			"Asset Spare Part",
			filters={"min_stock_qty": [">", 0]},
			fields=["name", "item_code", "default_warehouse", "min_stock_qty"],
			limit_page_length=0,
		)
		if not part.default_warehouse or part.default_warehouse in warehouses
	]
	if not parts:
		return []

	in_warehouse, in_company = defaultdict(float), defaultdict(float)
	for row in frappe.get_list(
		"Bin",
		filters={"item_code": ["in", list({part.item_code for part in parts})], "warehouse": ["in", list(warehouses) or [""]]},
		fields=["item_code", "warehouse", "actual_qty"],
		limit_page_length=0,
	):
		in_warehouse[(row.item_code, row.warehouse)] += flt(row.actual_qty)
		in_company[row.item_code] += flt(row.actual_qty)

	return sorted(
		part.name
		for part in parts
		if (in_warehouse[(part.item_code, part.default_warehouse)] if part.default_warehouse else in_company[part.item_code])
		< flt(part.min_stock_qty)
	)
