# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Master Data Overview" tab of the Master Data workspace.

One call returns everything the dashboard draws, so the page makes a single
round trip. Every figure goes through `frappe.get_list`, which applies the
caller's permissions: an area the user cannot read comes back marked
`restricted` instead of with a number, and user permissions narrow the counts
the same way they narrow the list view.

`AREAS` mirrors the cards on the Master Data workspace, in the same order, so
both tabs describe the same things. Each area is counted by the one DocType that
best answers "has this been set up?"; the card's other masters are listed
underneath it as `facts`.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_fullname, getdate, now_datetime, today

from a3_constructa.api.utils import company_filter, company_projects, default_company

AREAS = (
	{
		"card": "Company / Entity",
		"doctype": "Company",
		"unit": "Companies",
		"facts": (
			{"doctype": "Branch", "label": "Branches"},
			{"doctype": "Fiscal Year", "filters": {"disabled": 0}, "label": "Fiscal years"},
		),
	},
	{
		"card": "Project Master",
		"doctype": "Project",
		"unit": "Projects",
		"facts": (
			{"doctype": "Project", "filters": {"status": "Open"}, "label": "Open"},
			{"doctype": "Project Type", "label": "Project types"},
		),
	},
	{
		"card": "Cost Head / Package",
		"doctype": "Cost Head",
		"unit": "Cost heads",
		"facts": ({"doctype": "Cost Head", "filters": {"status": "Active"}, "label": "Active"},),
	},
	{
		"card": "WBS Master",
		"doctype": "WBS",
		"unit": "WBS elements",
		"facts": ({"doctype": "WBS", "filters": {"status": "Active"}, "label": "Active"},),
	},
	{
		"card": "Cost Code Master",
		"doctype": "Cost Code",
		"unit": "Cost codes",
		"facts": ({"doctype": "Cost Code", "filters": {"status": "Active"}, "label": "Active"},),
	},
	{
		"card": "Item Master",
		"doctype": "Item",
		"filters": {"disabled": 0},
		"unit": "Items",
		"facts": (
			{"doctype": "Item", "filters": {"disabled": 0, "is_mas": 1}, "label": "MAS"},
			{"doctype": "Item Group", "filters": {"is_group": 0}, "label": "Categories"},
		),
	},
	{
		"card": "Service Master",
		# Same definition as the "Service Items" report linked from this card.
		"doctype": "Item",
		"filters": {"disabled": 0, "is_stock_item": 0},
		"unit": "Service items",
		"facts": ({"doctype": "Subcontracting BOM", "label": "Subcontract BOMs"},),
	},
	{
		"card": "Vendor Master",
		"doctype": "Supplier",
		"filters": {"disabled": 0},
		"unit": "Vendors",
		"facts": (
			{"doctype": "Supplier Group", "label": "Groups"},
			{"doctype": "Payment Terms Template", "label": "Payment terms"},
		),
	},
	{
		"card": "Warehouse / Store",
		"doctype": "Warehouse",
		"filters": {"is_group": 0, "disabled": 0},
		"unit": "Stores",
		"facts": (
			{"doctype": "Warehouse", "filters": {"warehouse_type": "Site", "disabled": 0}, "label": "Site"},
			{"doctype": "Warehouse", "filters": {"warehouse_type": "Transit", "disabled": 0}, "label": "Transit"},
		),
	},
	{
		"card": "UOM Master",
		"doctype": "UOM",
		"filters": {"enabled": 1},
		"unit": "Units",
		"facts": (
			{"doctype": "UOM Category", "label": "Categories"},
			{"doctype": "UOM Conversion Factor", "label": "Conversions"},
		),
	},
	{
		"card": "Asset Category",
		"doctype": "Asset Category",
		"unit": "Categories",
		"facts": ({"doctype": "Vehicle", "label": "Vehicles"},),
	},
	{
		"card": "Location Master",
		"doctype": "Location",
		"unit": "Locations",
		"facts": ({"doctype": "Port", "filters": {"is_active": 1}, "label": "Ports"},),
	},
	{
		"card": "Shipping Line / Forwarder",
		# Same groups as the "Shipping Lines" and "Freight Forwarders" reports.
		"doctype": "Supplier",
		"filters": {"disabled": 0, "supplier_group": ["in", ["Shipping Line", "Freight Forwarder"]]},
		"unit": "Carriers",
		"facts": (
			{"doctype": "Service Route", "label": "Routes"},
			{"doctype": "Freight Rate Contract", "filters": {"status": "Active"}, "label": "Active contracts"},
		),
	},
	{
		"card": "Document Master",
		"doctype": "Document Type",
		"unit": "Document types",
		"facts": ({"doctype": "Mandatory Document Rule", "label": "Mandatory rules"},),
	},
	{
		"card": "Tax / Duty / Incoterm",
		"doctype": "Purchase Taxes and Charges Template",
		"filters": {"disabled": 0},
		"unit": "Tax templates",
		"facts": (
			{"doctype": "Incoterm", "label": "Incoterms"},
			{"doctype": "Customs Tariff Number", "label": "HS codes"},
		),
	},
	{
		"card": "Approval Matrix",
		"doctype": "Approval Matrix",
		"filters": {"is_active": 1},
		"unit": "Active rules",
		"facts": ({"doctype": "Workflow", "filters": {"is_active": 1}, "label": "Workflows"},),
	},
)

# The masters people actually key in. Reference data that ERPNext loads at
# setup (UOMs, currencies, countries, incoterms, the default item and supplier
# groups) is left out: it arrives in one burst on install day and would drown
# the activity figures.
ACTIVITY_DOCTYPES = (
	"Company",
	"Branch",
	"Project",
	"Cost Head",
	"WBS",
	"Cost Code",
	"Item",
	"Supplier",
	"Warehouse",
	"Asset Category",
	"Vehicle",
	"Location",
	"Port",
	"Service Route",
	"Freight Rate Contract",
	"Document Type",
	"Mandatory Document Rule",
	"Purchase Taxes and Charges Template",
	"Approval Matrix",
)

# Every check counts records that have a problem, so zero always means healthy.
# `critical` is reserved for gaps that put a transaction in the wrong place
# downstream, or keep an expired contract in use.
HEALTH_CHECKS = (
	{
		# Stock Entry lines take their expense account from the cost code
		# (overrides/stock_entry.py). An unmapped code does not stop the entry;
		# the line quietly keeps ERPNext's default account, usually Stock
		# Adjustment, and the project's consumption lands in the wrong ledger.
		"label": "Active cost codes with no account",
		"doctype": "Cost Code",
		"filters": {"status": "Active", "account": ["is", "not set"]},
		"severity": "critical",
	},
	{
		"label": "Rate contracts past validity but still active",
		"doctype": "Freight Rate Contract",
		"filters": {"status": "Active", "valid_to": ["<", "{today}"]},
		"severity": "critical",
	},
	{
		"label": "Rate contracts expiring in 30 days",
		"doctype": "Freight Rate Contract",
		"filters": {"status": "Active", "valid_to": ["between", ["{today}", "{today+30}"]]},
		"severity": "warning",
	},
	{
		"label": "Open projects with no location",
		"doctype": "Project",
		"filters": {"status": "Open", "location": ["is", "not set"]},
		"severity": "warning",
	},
	{
		"label": "WBS elements with no project",
		"doctype": "WBS",
		"filters": {"project": ["is", "not set"]},
		"severity": "warning",
	},
	{
		"label": "Cost heads with no project",
		"doctype": "Cost Head",
		"filters": {"project": ["is", "not set"]},
		"severity": "warning",
	},
	{
		"label": "Vendors with no country",
		"doctype": "Supplier",
		"filters": {"disabled": 0, "country": ["is", "not set"]},
		"severity": "warning",
	},
	{
		"label": "Vendors with no payment terms",
		"doctype": "Supplier",
		"filters": {"disabled": 0, "payment_terms": ["is", "not set"]},
		"severity": "warning",
	},
	{
		"label": "Stock items with no HS code",
		"doctype": "Item",
		"filters": {"disabled": 0, "is_stock_item": 1, "customs_tariff_number": ["is", "not set"]},
		"severity": "warning",
	},
)

BREAKDOWNS = (
	{"title": "Items by category", "doctype": "Item", "field": "item_group", "filters": {"disabled": 0}},
	{"title": "Vendors by group", "doctype": "Supplier", "field": "supplier_group", "filters": {"disabled": 0}},
	{"title": "Projects by status", "doctype": "Project", "field": "status"},
	{
		"title": "Stores by type",
		"doctype": "Warehouse",
		"field": "warehouse_type",
		"filters": {"is_group": 0, "disabled": 0},
	},
)

TREND_MONTHS = 12
RECENT_LIMIT = 8
# A breakdown shows this many named rows; the rest fold into "Other".
BREAKDOWN_ROWS = 5


@frappe.whitelist()
def get_overview() -> dict:
	readable = {doctype for doctype in _all_doctypes() if _can_read(doctype)}
	checks = [_health_check(check, readable) for check in HEALTH_CHECKS] + _new_master_checks()
	activity = [doctype for doctype in ACTIVITY_DOCTYPES if doctype in readable]

	return {
		"generated_at": now_datetime(),
		"areas": [_area(area, readable) for area in AREAS],
		"kpis": _kpis(activity, readable),
		"health": sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical")),
		"recent": _recent(activity),
		"trend": _trend(activity),
		"breakdowns": [_breakdown(b, readable) for b in BREAKDOWNS],
	}


def _all_doctypes() -> set[str]:
	doctypes = set(ACTIVITY_DOCTYPES)
	for area in AREAS:
		doctypes.add(area["doctype"])
		doctypes.update(fact["doctype"] for fact in area["facts"])
	doctypes.update(check["doctype"] for check in HEALTH_CHECKS)
	doctypes.update(b["doctype"] for b in BREAKDOWNS)
	return doctypes


def _can_read(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, "read")


def _count(doctype: str, filters=None) -> int:
	return frappe.get_list(doctype, filters=_scoped(doctype, filters), fields=["count(name) as n"])[0].n


def _scoped(doctype: str, filters=None) -> dict:
	"""Company-bearing masters (projects, warehouses, tax templates) count for the
	default company only; shared masters such as items and suppliers count whole."""
	scoped = dict(filters or {})
	if doctype != "Company":
		scoped.update(company_filter(doctype, default_company()))
	return scoped


def _area(area: dict, readable: set) -> dict:
	doctype = area["doctype"]
	filters = area.get("filters") or {}
	result = {
		"card": _(area["card"]),
		"unit": _(area["unit"]),
		"doctype": doctype,
		"filters": filters,
		"restricted": doctype not in readable,
		"count": None,
		"last_modified": None,
		"facts": [],
	}
	if result["restricted"]:
		return result

	result["count"] = _count(doctype, filters)
	if result["count"]:
		result["last_modified"] = frappe.get_list(
			doctype, filters=_scoped(doctype, filters), fields=["max(modified) as m"]
		)[0].m

	for fact in area["facts"]:
		fact_filters = fact.get("filters") or {}
		result["facts"].append(
			{
				"label": _(fact["label"]),
				"doctype": fact["doctype"],
				"filters": fact_filters,
				"count": _count(fact["doctype"], fact_filters) if fact["doctype"] in readable else None,
			}
		)
	return result


def _kpis(activity: list[str], readable: set) -> dict:
	now = today()
	month_ago = add_days(now, -30)
	two_months_ago = add_days(now, -60)

	added = previous = edited = 0
	for doctype in activity:
		added += _count(doctype, {"creation": [">=", month_ago]})
		previous += _count(doctype, {"creation": ["between", [two_months_ago, add_days(month_ago, -1)]]})
		edited += _count(doctype, {"creation": ["<", month_ago], "modified": [">=", month_ago]})

	projects = "Project" in readable
	return {
		"added_30d": added,
		"added_prev_30d": previous,
		"edited_30d": edited,
		"active_projects": _count("Project", {"status": "Open"}) if projects else None,
		"total_projects": _count("Project") if projects else None,
	}


def _health_check(check: dict, readable: set) -> dict:
	filters = _resolve_dates(check["filters"])
	return {
		"label": _(check["label"]),
		"doctype": check["doctype"],
		"filters": filters,
		"severity": check["severity"],
		"count": _count(check["doctype"], filters) if check["doctype"] in readable else None,
	}


# ---------------------------------------------------------------- newer masters
# Crews (P-07A), alert rules (P-13F) and estimate prices (P-02C) live on other
# workspaces' cards, but bad data in them is a master-data problem: a crew with
# no foreman, an alert nobody receives, an estimate line with no price. A child
# table cannot be filtered from a list URL, so these name the records they found.


def _named(label, doctype, names, readable, meta=None) -> dict:
	names = sorted(set(names or []))
	return {
		"label": _(label),
		"doctype": doctype,
		"filters": {"name": ["in", names]},
		"severity": "warning",
		"count": len(names) if readable else None,
		"meta": meta,
	}


def _new_master_checks() -> list[dict]:
	return _crew_checks() + _alert_rule_checks() + _estimate_checks()


def _crew_checks() -> list[dict]:
	readable = _can_read("Crew")
	no_foreman, unpriced, workers = [], [], []
	if readable:
		active = _scoped("Crew", {"is_active": 1})
		no_foreman = frappe.get_list("Crew", filters={**active, "foreman": ["is", "not set"]}, pluck="name", limit_page_length=0)
		members = frappe.get_list(
			"Crew",
			filters=[["Crew", field, *(v if isinstance(v, list) else ["=", v])] for field, v in active.items()]
			+ [["Crew Member", "is_active", "=", 1]],
			fields=["name", "`tabCrew Member`.employee as employee", "`tabCrew Member`.daily_rate as daily_rate"],
			limit_page_length=0,
		)
		unpriced = [m.name for m in members if not flt(m.daily_rate)]
		crews_of = {}
		for m in members:
			crews_of.setdefault(m.employee, set()).add(m.name)
		workers = [employee for employee, crews in crews_of.items() if len(crews) > 1]
	employees = _can_read("Employee")
	return [
		_named("Active crews with no foreman", "Crew", no_foreman, readable),
		_named("Active crews with members on no daily rate", "Crew", unpriced, readable,
		       _("The crew's daily cost leaves them out")),
		_named("Workers active in more than one crew", "Employee" if employees else "Crew",
		       workers if employees else [], readable and employees, _("Their hours split between the crews")),
	]


def _alert_rule_checks() -> list[dict]:
	from a3_constructa.api.alerts import recipients

	readable = _can_read("Alert Rule")
	nobody, never = [], []
	if readable:
		for rule in frappe.get_list("Alert Rule", filters={"is_active": 1}, fields=["name", "last_run"], limit_page_length=0):
			if not rule.last_run:
				never.append(rule.name)
			if not recipients(frappe.get_doc("Alert Rule", rule.name)):
				nobody.append(rule.name)
	return [
		_named("Active alert rules nobody receives", "Alert Rule", nobody, readable,
		       _("Every recipient disabled, or a role with no users")),
		_named("Active alert rules that have never run", "Alert Rule", never, readable,
		       _("The scheduler runs them daily or weekly")),
	]


def _estimate_checks() -> list[dict]:
	readable = _can_read("Estimate Sheet")
	unpriced, no_output = [], []
	if readable:
		# Sheets carry neither company nor project: they are the company's through
		# their BOQ's project, and a tender BOQ (no project yet) counts for everyone.
		company = default_company()
		boqs = None
		if company:
			boqs = frappe.get_all("BOQ", filters={"project": ["in", company_projects(company) or [""]]}, pluck="name")
			boqs += frappe.get_all("BOQ", filters={"project": ["is", "not set"]}, pluck="name")
		filters = [["Estimate Sheet", "docstatus", "<", 2], ["Estimate Resource", "resource_type", "is", "set"]]
		if boqs is not None:
			filters.append(["Estimate Sheet", "boq", "in", boqs or [""]])
		for line in frappe.get_list(
			"Estimate Sheet",
			filters=filters,
			fields=["name", "`tabEstimate Resource`.resource_type as kind", "`tabEstimate Resource`.rate as rate",
			        "`tabEstimate Resource`.output_per_day as output_per_day"],
			limit_page_length=0,
		):
			if not flt(line.rate):
				unpriced.append(line.name)
			if line.kind in ("Labour", "Equipment") and not flt(line.output_per_day):
				no_output.append(line.name)
	return [
		_named("Estimate sheets with resource lines at no rate", "Estimate Sheet", unpriced, readable,
		       _("Fetch prices, or type a rate")),
		_named("Estimate sheets with labour or plant lines at no output per day", "Estimate Sheet", no_output, readable,
		       _("Their cost per unit works out at zero")),
	]


def _resolve_dates(filters: dict) -> dict:
	"""Fill the `{today}` placeholders, so a check means the same thing whichever day it runs."""
	now = getdate(today())
	values = {"{today}": str(now), "{today+30}": str(add_days(now, 30))}

	def resolve(value):
		if isinstance(value, list):
			return [resolve(v) for v in value]
		return values.get(value, value)

	return {field: resolve(value) for field, value in filters.items()}


def _recent(activity: list[str]) -> list[dict]:
	rows = []
	for doctype in activity:
		title_field = frappe.get_meta(doctype).get_title_field()
		fields = ["name", "creation", "owner"]
		if title_field != "name":
			fields.append(f"{title_field} as title")
		for row in frappe.get_list(doctype, filters=_scoped(doctype), fields=fields, order_by="creation desc", limit=RECENT_LIMIT):
			rows.append(
				{
					"doctype": doctype,
					"name": row.name,
					"title": row.get("title") or row.name,
					"creation": row.creation,
					"owner": get_fullname(row.owner),
				}
			)
	rows.sort(key=lambda r: r["creation"], reverse=True)
	return rows[:RECENT_LIMIT]


def _trend(activity: list[str]) -> list[dict]:
	first = getdate(get_first_day(add_months(today(), -(TREND_MONTHS - 1))))
	months = [getdate(add_months(first, i)) for i in range(TREND_MONTHS)]
	counts = dict.fromkeys((m.strftime("%Y-%m") for m in months), 0)

	for doctype in activity:
		for row in frappe.get_list(
			doctype,
			filters=_scoped(doctype, {"creation": [">=", first]}),
			fields=["date_format(creation, '%Y-%m') as month", "count(name) as n"],
			group_by="month",
			order_by="month asc",
		):
			if row.month in counts:
				counts[row.month] += row.n

	return [
		{"month": m.strftime("%Y-%m"), "label": m.strftime("%b %Y"), "short": m.strftime("%b"), "count": counts[m.strftime("%Y-%m")]}
		for m in months
	]


def _breakdown(breakdown: dict, readable: set) -> dict:
	doctype, field = breakdown["doctype"], breakdown["field"]
	filters = breakdown.get("filters") or {}
	result = {
		"title": _(breakdown["title"]),
		"doctype": doctype,
		"field": field,
		"filters": filters,
		"restricted": doctype not in readable,
		"rows": [],
		"total": 0,
	}
	if result["restricted"]:
		return result

	groups = frappe.get_list(
		doctype,
		filters=_scoped(doctype, filters),
		fields=[f"{field} as value", "count(name) as n"],
		group_by=field,
		order_by="n desc",
	)
	groups.sort(key=lambda g: (-g.n, g.value or ""))

	rows = [{"value": g.value, "label": g.value or _("Not set"), "count": g.n} for g in groups[:BREAKDOWN_ROWS]]
	rest = groups[BREAKDOWN_ROWS:]
	if rest:
		rows.append({"value": None, "label": _("Other"), "count": sum(g.n for g in rest), "other": True})

	result["rows"] = rows
	result["total"] = sum(g.n for g in groups)
	return result
