# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Delivery & Logistics Overview" tab of the Delivery & Logistics workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency.

Shipments are Shipment Tracking records. One is on the way until it reaches a
status in SHIPMENT_DONE; drafts count, because a shipment carries a live status
while it waits for the original documents it needs before it can be submitted.
Receipts are submitted Purchase Receipts, a site receipt (SMRN) being one with
`is_site_receipt` set.
"""

from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, flt, getdate, now_datetime, today

from a3_constructa.api.award_procurement import SHIPMENT_DONE
from a3_constructa.api.procurement_overview import SHIPMENT_STATUSES
from a3_constructa.api.utils import company_projects, default_company, default_currency

ON_THE_WAY = {"docstatus": ["<", 2], "status": ["not in", list(SHIPMENT_DONE)]}
IN_PORT = ("Arrived at Port", "Under Customs Clearance")
DELIVERY_MODES = ("Direct to Warehouse", "Direct to Site")

# The Demurrage & Detention report already knows which rate contract sets a
# container's free days; the folder name's "&" means it is loaded by path.
FREE_DAYS = "a3_constructa.a3_constructa.report.demurrage_&_detention.demurrage_&_detention.get_free_days"

CUSTOMS_WAIT_DAYS = 7
ARRIVING_NEXT = 8
TOP_PROJECTS = 5
TOP_SUPPLIERS = 5


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {dt for dt in ("Shipment Tracking", "Purchase Receipt") if frappe.has_permission(dt, "read")}
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"shipments": _shipments(readable, now),
		"customs": _customs(readable, now),
		"transit": _transit(readable, now),
		"costs": _costs(readable, now),
		"receipts": _receipts(readable, now),
		"health": _health(readable, now),
	}


def _scoped(doctype, filters=None):
	"""`filters` narrowed to the default company, as a list of conditions."""
	if isinstance(filters, dict):
		conditions = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
	else:
		conditions = list(filters or [])
	company = default_company()
	if company:
		if frappe.get_meta(doctype).has_field("company"):
			conditions.append([doctype, "company", "=", company])
		elif frappe.get_meta(doctype).has_field("project"):
			conditions.append([doctype, "project", "in", company_projects(company) or [""]])
	return conditions


def _count(doctype, filters=None) -> int:
	return frappe.get_list(doctype, filters=_scoped(doctype, filters), fields=["count(name) as n"])[0].n


def _statuses(doctype, order, filters=None) -> list[dict]:
	found = {
		row.status: row.n
		for row in frappe.get_list(
			doctype, filters=_scoped(doctype, filters), fields=["status", "count(name) as n"], group_by="status"
		)
	}
	return [{"label": _(status), "value": status, "count": found[status]} for status in order if found.get(status)]


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


# ---------------------------------------------------------------- sections


def _shipments(readable, now) -> dict:
	if "Shipment Tracking" not in readable:
		return {"restricted": True}

	active = frappe.get_list(
		"Shipment Tracking",
		filters=_scoped("Shipment Tracking", ON_THE_WAY),
		fields=[
			"name",
			"supplier",
			"project",
			"status",
			"shipment_type",
			"delivery_mode",
			"expected_receipt_date",
			"eta_discharge",
		],
		limit_page_length=0,
	)
	for row in active:
		# An import with no promised receipt date is at least due when it docks.
		row.due = row.expected_receipt_date or (row.eta_discharge if row.shipment_type == "Import" else None)
		row.late = bool(row.expected_receipt_date and getdate(row.expected_receipt_date) < now)

	arriving = sorted(active, key=lambda row: (row.due is None, row.due or now, row.name))[:ARRIVING_NEXT]

	modes = Counter(row.delivery_mode or None for row in active)
	by_mode = [{"label": _(mode), "value": mode, "count": modes[mode]} for mode in DELIVERY_MODES if modes.get(mode)]
	if modes.get(None):
		by_mode.append({"label": _("Not set"), "value": None, "count": modes[None]})

	projects = Counter(row.project for row in active)
	titles = _project_titles(list(projects))
	by_project = _top(
		[{"label": titles.get(name) or name, "value": name, "count": n} for name, n in projects.items()], TOP_PROJECTS
	)

	return {
		"restricted": False,
		"filters": ON_THE_WAY,
		"active": len(active),
		"import_count": sum(1 for row in active if row.shipment_type == "Import"),
		"domestic_count": sum(1 for row in active if row.shipment_type == "Domestic"),
		"late_count": sum(1 for row in active if row.late),
		"import_by_status": _statuses("Shipment Tracking", SHIPMENT_STATUSES, {**ON_THE_WAY, "shipment_type": "Import"}),
		"domestic_by_status": _statuses("Shipment Tracking", SHIPMENT_STATUSES, {**ON_THE_WAY, "shipment_type": "Domestic"}),
		"by_mode": by_mode,
		"by_project": by_project,
		"arriving": [
			{key: row[key] for key in ("name", "supplier", "status", "shipment_type", "due", "late")}
			for row in arriving
		],
	}


def _project_titles(names: list[str]) -> dict:
	if not names or not frappe.has_permission("Project", "read"):
		return {}
	return {
		row.name: row.project_name
		for row in frappe.get_list("Project", filters={"name": ["in", names]}, fields=["name", "project_name"])
	}


def _customs(readable, now) -> dict:
	if "Shipment Tracking" not in readable:
		return {"restricted": True}
	in_port = {"docstatus": ["<", 2], "status": ["in", list(IN_PORT)]}
	oldest = frappe.get_list(
		"Shipment Tracking", filters=_scoped("Shipment Tracking", in_port), fields=["min(ata_discharge) as d"]
	)[0].d
	return {
		"restricted": False,
		"count": _count("Shipment Tracking", in_port),
		"oldest_days": date_diff(now, oldest) if oldest else None,
	}


def _transit(readable, now) -> dict:
	if "Shipment Tracking" not in readable:
		return {"restricted": True}
	arrived = {
		"docstatus": ["<", 2],
		"shipment_type": "Import",
		"ata_discharge": [">=", str(add_months(now, -12))],
		"transit_days": [">", 0],
	}
	row = frappe.get_list(
		"Shipment Tracking",
		filters=_scoped("Shipment Tracking", arrived),
		fields=["avg(transit_days) as average", "count(name) as n"],
	)[0]
	return {"restricted": False, "average": flt(row.average, 1), "count": row.n}


def _costs(readable, now) -> dict:
	if "Shipment Tracking" not in readable:
		return {"restricted": True}
	rows = frappe.get_list(
		"Shipment Tracking",
		filters=_scoped("Shipment Tracking", {"docstatus": ["<", 2], "ata_discharge": [">=", str(add_months(now, -12))]}),
		fields=["demurrage_amount", "detention_amount", "demurrage_days"],
		limit_page_length=0,
	)
	demurrage = sum(flt(row.demurrage_amount) for row in rows)
	detention = sum(flt(row.detention_amount) for row in rows)
	return {
		"restricted": False,
		"demurrage": demurrage,
		"detention": detention,
		"total": demurrage + detention,
		"days": sum(int(row.demurrage_days or 0) for row in rows),
		"count": sum(1 for row in rows if flt(row.demurrage_amount) or flt(row.detention_amount)),
	}


def _receipts(readable, now) -> dict:
	if "Purchase Receipt" not in readable:
		return {"restricted": True}

	month = {"docstatus": 1, "posting_date": [">=", str(add_days(now, -30))]}
	recent = {
		bool(row.is_site_receipt): row
		for row in frappe.get_list(
			"Purchase Receipt",
			filters=_scoped("Purchase Receipt", month),
			fields=["is_site_receipt", "sum(base_net_total) as total", "count(name) as n"],
			group_by="is_site_receipt",
		)
	}

	year = {"docstatus": 1, "posting_date": [">=", str(add_months(now, -12))]}
	suppliers = [
		{"label": row.supplier, "value": row.supplier, "count": row.n, "amount": flt(row.amount)}
		for row in frappe.get_list(
			"Purchase Receipt",
			filters=_scoped("Purchase Receipt", year),
			fields=["supplier", "sum(base_net_total) as amount", "count(name) as n"],
			group_by="supplier",
		)
	]
	destinations = {
		bool(row.is_site_receipt): row
		for row in frappe.get_list(
			"Purchase Receipt",
			filters=_scoped("Purchase Receipt", year),
			fields=["is_site_receipt", "sum(base_net_total) as amount", "count(name) as n"],
			group_by="is_site_receipt",
		)
	}
	by_destination = [
		{"label": label, "value": int(site), "count": destinations[site].n, "amount": flt(destinations[site].amount)}
		for site, label in ((False, _("Warehouse (GRN)")), (True, _("Site (SMRN)")))
		if site in destinations
	]

	def part(site, field):
		row = recent.get(site)
		return flt(row[field]) if row else 0

	return {
		"restricted": False,
		"value_30d": part(False, "total") + part(True, "total"),
		"warehouse_30d": int(part(False, "n")),
		"site_30d": int(part(True, "n")),
		"year_filters": year,
		"suppliers": _top(suppliers, TOP_SUPPLIERS, measure="amount"),
		"suppliers_total": sum(row["amount"] for row in suppliers),
		"by_destination": by_destination,
		"destination_total": sum(row["amount"] for row in by_destination),
	}


def _health(readable, now) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for receipt dates already missed.
	"""
	checks = []
	st = "Shipment Tracking" in readable

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append(
			{"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta}
		)

	late = {**ON_THE_WAY, "expected_receipt_date": ["<", str(now)]}
	check("Shipments past their expected receipt date", "critical", "Shipment Tracking", _count("Shipment Tracking", late) if st else None, late)

	stuck = {
		"docstatus": ["<", 2],
		"shipment_type": "Import",
		"status": ["in", list(IN_PORT)],
		"ata_discharge": ["<", str(add_days(now, -CUSTOMS_WAIT_DAYS))],
	}
	check(
		f"Imports in port or customs over {CUSTOMS_WAIT_DAYS} days",
		"warning",
		"Shipment Tracking",
		_count("Shipment Tracking", stuck) if st else None,
		stuck,
	)

	waiting = None
	if st:
		waiting = sorted(
			set(
				frappe.get_list(
					"Shipment Tracking",
					filters=_scoped(
						"Shipment Tracking",
						[["Shipment Tracking", "docstatus", "<", 2], ["Shipment Document", "is_original_received", "=", 0]],
					),
					pluck="name",
					limit_page_length=0,
				)
			)
		)
	check(
		"Shipments still waiting on original documents",
		"warning",
		"Shipment Tracking",
		len(waiting) if waiting is not None else None,
		{"name": ["in", waiting or []]},
	)

	held = None
	if st:
		free_days = frappe.get_attr(FREE_DAYS)()
		held = []
		for row in frappe.get_list(
			"Shipment Tracking",
			filters=_scoped(
				"Shipment Tracking",
				{
					"docstatus": ["<", 2],
					"shipment_type": "Import",
					"ata_discharge": ["is", "set"],
					"container_return_date": ["is", "not set"],
				},
			),
			fields=["name", "shipping_line", "service_route", "ata_discharge"],
			limit_page_length=0,
		):
			free = free_days.get((row.shipping_line, row.service_route))
			# No rate contract, no free days to measure against.
			if free is not None and date_diff(now, row.ata_discharge) > free:
				held.append(row.name)
	check(
		"Containers held past their free days",
		"warning",
		"Shipment Tracking",
		len(held) if held is not None else None,
		{"name": ["in", held or []]},
		meta=_("Free days from the freight rate contract"),
	)

	unreceipted = {"docstatus": ["<", 2], "status": ["in", list(SHIPMENT_DONE)], "purchase_receipt": ["is", "not set"]}
	check(
		"Received shipments with no purchase receipt linked",
		"warning",
		"Shipment Tracking",
		_count("Shipment Tracking", unreceipted) if st else None,
		unreceipted,
	)

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
