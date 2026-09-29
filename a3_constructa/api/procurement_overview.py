# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Procurement Overview" tab of the Procurement workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency, from the
documents' base amounts.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, flt, getdate, now_datetime, today

from a3_constructa.api.award_procurement import OPEN_PO_STATUSES, SHIPMENT_DONE, active_awards, award_rows
from a3_constructa.api.boq_procurement import can_trace
from a3_constructa.api.utils import company_projects, default_company, default_currency

MR_STATUSES = ("Draft", "Pending", "Partially Ordered", "Ordered", "Partially Received", "Received", "Stopped")
RFQ_STATUSES = ("Draft", "Submitted")
SQ_STATUSES = ("Draft", "Submitted", "Expired", "Stopped")
PO_STATUSES = ("Draft", "On Hold", "To Receive and Bill", "To Receive", "To Bill", "Completed", "Closed")
SHIPMENT_STATUSES = (
	"Draft",
	"Supplier Despatched",
	"In Transit",
	"Arrived at Port",
	"Under Customs Clearance",
	"Cleared",
	"In Inland Transit",
)

REQUEST_WAIT_DAYS = 14
RFQ_WAIT_DAYS = 7
TOP_SUPPLIERS = 5
RECENT_ORDERS = 8


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {
		dt
		for dt in (
			"Material Request",
			"Request for Quotation",
			"Supplier Quotation",
			"Purchase Order",
			"Awarded Quotation",
			"Shipment Tracking",
		)
		if frappe.has_permission(dt, "read")
	}
	awards = _awards(readable)
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"orders": _orders(readable, now),
		"requests": _requests(readable, now),
		"quotes": _quotes(readable),
		"awards": awards,
		"shipments": _shipments(readable),
		"health": _health(readable, now, awards),
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


# ---------------------------------------------------------------- sections


def _orders(readable, now) -> dict:
	if "Purchase Order" not in readable:
		return {"restricted": True}

	# What is still to arrive on open orders, valued at the order's own rate.
	open_value = 0.0
	open_orders = set()
	for row in frappe.get_list(
		"Purchase Order",
		filters=_scoped("Purchase Order", [["Purchase Order", "docstatus", "=", 1], ["Purchase Order", "status", "in", OPEN_PO_STATUSES]]),
		fields=[
			"name",
			"`tabPurchase Order Item`.qty as qty",
			"`tabPurchase Order Item`.received_qty as received_qty",
			"`tabPurchase Order Item`.base_net_rate as rate",
		],
		limit_page_length=0,
	):
		open_orders.add(row.name)
		open_value += max(0.0, flt(row.qty) - flt(row.received_qty)) * flt(row.rate)

	late = {"docstatus": 1, "status": ["in", OPEN_PO_STATUSES], "schedule_date": ["<", now]}
	month_ago = add_days(now, -30)
	ordered_30d = frappe.get_list(
		"Purchase Order",
		filters=_scoped("Purchase Order", {"docstatus": 1, "transaction_date": [">=", month_ago]}),
		fields=["sum(base_net_total) as total", "count(name) as n"],
	)[0]

	suppliers = frappe.get_list(
		"Purchase Order",
		filters=_scoped("Purchase Order", {"docstatus": 1, "transaction_date": [">=", add_months(now, -12)]}),
		fields=["supplier", "sum(base_net_total) as amount", "count(name) as n"],
		group_by="supplier",
	)
	suppliers.sort(key=lambda s: -flt(s.amount))
	top = [
		{"label": s.supplier, "value": s.supplier, "count": s.n, "amount": flt(s.amount)} for s in suppliers[:TOP_SUPPLIERS]
	]
	rest = suppliers[TOP_SUPPLIERS:]
	if rest:
		top.append(
			{"label": _("Other"), "value": None, "count": sum(s.n for s in rest), "amount": sum(flt(s.amount) for s in rest), "other": True}
		)

	recent = frappe.get_list(
		"Purchase Order",
		filters=_scoped("Purchase Order", {"docstatus": ["<", 2]}),
		fields=["name", "supplier", "transaction_date", "schedule_date", "status", "base_net_total", "per_received"],
		order_by="creation desc",
		limit_page_length=RECENT_ORDERS,
	)

	return {
		"restricted": False,
		"open_value": open_value,
		"open_count": len(open_orders),
		"late_count": _count("Purchase Order", late),
		"ordered_30d": flt(ordered_30d.total),
		"ordered_30d_count": ordered_30d.n,
		"by_status": _statuses("Purchase Order", PO_STATUSES, {"docstatus": ["<", 2]}),
		"suppliers": top,
		"suppliers_total": sum(flt(s.amount) for s in suppliers),
		"recent": recent,
	}


def _requests(readable, now) -> dict:
	if "Material Request" not in readable:
		return {"restricted": True}

	waiting = {
		"docstatus": 1,
		"material_request_type": "Purchase",
		"per_ordered": ["<", 100],
		"status": ["not in", ["Stopped", "Cancelled"]],
	}
	oldest = frappe.get_list("Material Request", filters=_scoped("Material Request", waiting), fields=["min(transaction_date) as d"])[0].d
	return {
		"restricted": False,
		"waiting_count": _count("Material Request", waiting),
		"waiting_filters": waiting,
		"oldest_days": date_diff(now, oldest) if oldest else 0,
		"by_status": _statuses(
			"Material Request", MR_STATUSES, {"material_request_type": "Purchase", "docstatus": ["<", 2]}
		),
	}


def _quotes(readable) -> dict:
	result = {"rfq_restricted": "Request for Quotation" not in readable, "sq_restricted": "Supplier Quotation" not in readable}
	if not result["rfq_restricted"]:
		result["rfq_by_status"] = _statuses("Request for Quotation", RFQ_STATUSES, {"docstatus": ["<", 2]})
	if not result["sq_restricted"]:
		result["sq_by_status"] = _statuses("Supplier Quotation", SQ_STATUSES, {"docstatus": ["<", 2]})
	return result


def _awards(readable) -> dict:
	if "Awarded Quotation" not in readable or not can_trace():
		return {"restricted": True, "rows": []}
	rows, lines = award_rows(active_awards())
	traced = sorted({mri for line in lines for mri in line["_material_request_items"]})
	over = [line for line in lines if line["requested_qty"] + line["draft_qty"] > line["approved_qty"] + 1e-6]
	return {
		"restricted": False,
		"rows": rows,
		"budget": sum(row["budget"] for row in rows),
		"committed": sum(row["committed"] for row in rows),
		"ordered": (
			sum(row["budget"] * row["ordered"] for row in rows) / sum(row["budget"] for row in rows)
			if sum(row["budget"] for row in rows)
			else 0
		),
		"over_requested": len(over),
		"_traced_request_lines": traced,
	}


def _shipments(readable) -> dict:
	if "Shipment Tracking" not in readable:
		return {"restricted": True}
	on_the_way = {"docstatus": ["<", 2], "status": ["not in", SHIPMENT_DONE]}
	rows = _statuses("Shipment Tracking", SHIPMENT_STATUSES, on_the_way)
	return {"restricted": False, "by_status": rows, "active": sum(row["count"] for row in rows)}


def _health(readable, now, awards) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for delivery dates a supplier has already missed.
	"""
	checks = []

	def check(label, severity, doctype, count, filters=None, report=None, meta=None):
		checks.append(
			{"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "report": report, "meta": meta}
		)

	po = "Purchase Order" in readable
	late = {"docstatus": 1, "status": ["in", OPEN_PO_STATUSES], "schedule_date": ["<", str(now)]}
	check("Purchase orders past their delivery date", "critical", "Purchase Order", _count("Purchase Order", late) if po else None, late)

	stale_request = {
		"docstatus": 1,
		"material_request_type": "Purchase",
		"per_ordered": ["<", 100],
		"status": ["not in", ["Stopped", "Cancelled"]],
		"transaction_date": ["<", str(add_days(now, -REQUEST_WAIT_DAYS))],
	}
	check(
		f"Material requests waiting over {REQUEST_WAIT_DAYS} days for an order",
		"warning",
		"Material Request",
		_count("Material Request", stale_request) if "Material Request" in readable else None,
		stale_request,
	)

	unanswered = None
	if "Request for Quotation" in readable and "Supplier Quotation" in readable:
		sent = set(
			frappe.get_list(
				"Request for Quotation",
				filters=_scoped("Request for Quotation", {"docstatus": 1, "transaction_date": ["<", str(add_days(now, -RFQ_WAIT_DAYS))]}),
				pluck="name",
			)
		)
		answered = {
			row.rfq
			for row in frappe.get_list(
				"Supplier Quotation",
				filters=[["Supplier Quotation Item", "request_for_quotation", "in", sorted(sent)], ["Supplier Quotation", "docstatus", "<", 2]],
				fields=["`tabSupplier Quotation Item`.request_for_quotation as rfq"],
				limit_page_length=0,
			)
		} if sent else set()
		unanswered = sent - answered
	check(
		f"RFQs with no quotation after {RFQ_WAIT_DAYS} days",
		"warning",
		"Request for Quotation",
		len(unanswered) if unanswered is not None else None,
		{"name": ["in", sorted(unanswered or [])]},
	)

	not_ordered = None
	if "Supplier Quotation" in readable and po:
		recommended = set(
			frappe.get_list("Supplier Quotation", filters=_scoped("Supplier Quotation", {"docstatus": 1, "is_recommended": 1}), pluck="name")
		)
		ordered = {
			row.sq
			for row in frappe.get_list(
				"Purchase Order",
				filters=[["Purchase Order Item", "supplier_quotation", "in", sorted(recommended)], ["Purchase Order", "docstatus", "<", 2]],
				fields=["`tabPurchase Order Item`.supplier_quotation as sq"],
				limit_page_length=0,
			)
		} if recommended else set()
		not_ordered = recommended - ordered
	check(
		"Recommended quotations not yet ordered",
		"warning",
		"Supplier Quotation",
		len(not_ordered) if not_ordered is not None else None,
		{"name": ["in", sorted(not_ordered or [])]},
	)

	restricted = awards["restricted"]
	check(
		"BOQ lines requested beyond what was approved",
		"warning",
		"BOQ",
		None if restricted else awards["over_requested"],
		{"stage": "Over requested"},
		report="Award Procurement Status",
	)

	nothing_requested = None if restricted else [row["name"] for row in awards["rows"] if row["lines"] and not row["requested"]]
	check(
		"Awards with an approved BOQ and nothing requested",
		"warning",
		"Awarded Quotation",
		None if restricted else len(nothing_requested),
		{"name": ["in", nothing_requested or []]},
	)

	off_boq = None
	if not restricted and po:
		projects = sorted({row["project"] for row in awards["rows"] if row["project"]})
		traced = set(awards["_traced_request_lines"])
		off_boq = set()
		if projects:
			for row in frappe.get_list(
				"Purchase Order",
				filters=[["Purchase Order", "docstatus", "=", 1], ["Purchase Order Item", "project", "in", projects]],
				fields=["name", "`tabPurchase Order Item`.material_request_item as mri"],
				limit_page_length=0,
			):
				if row.mri not in traced:
					off_boq.add(row.name)
	check(
		"Orders for awarded projects placed outside the BOQ",
		"warning",
		"Purchase Order",
		len(off_boq) if off_boq is not None else None,
		{"name": ["in", sorted(off_boq or [])]},
	)

	awards.pop("_traced_request_lines", None)
	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
