# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Every approved BOQ line of an award, project or BOQ, and how far it has been bought.

The figures come from a3_constructa.api.boq_procurement, the same place the
award procurement page and the Procurement overview read them from.
"""

import frappe
from frappe import _

from a3_constructa.api.boq_procurement import approved_boqs, boq_lines, can_trace, coverage

STAGES = {
	"To request": lambda line: line["to_request"] > 0,
	"To order": lambda line: line["to_order"] > 0,
	"To receive": lambda line: line["to_receive"] > 0,
	"Fully received": lambda line: line["approved_qty"] > 0 and line["received_qty"] >= line["approved_qty"],
	"Over requested": lambda line: line["requested_qty"] + line["draft_qty"] > line["approved_qty"] + 1e-6,
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not can_trace():
		frappe.throw(
			_("This report needs read access to BOQs, Material Requests, Purchase Orders and Purchase Receipts."),
			frappe.PermissionError,
		)

	boqs = approved_boqs(filters.awarded_quotation, filters.project)
	if filters.boq:
		boqs = [boq for boq in boqs if boq == filters.boq]
	lines = boq_lines(boqs)
	if filters.item_code:
		lines = [line for line in lines if line["item_code"] == filters.item_code]
	if filters.stage in STAGES:
		lines = [line for line in lines if STAGES[filters.stage](line)]

	for line in lines:
		line["ordered_percent"] = (
			min(100, line["ordered_qty"] / line["approved_qty"] * 100) if line["approved_qty"] else 0
		)

	return get_columns(), lines, None, None, get_summary(lines)


def get_summary(lines):
	totals = coverage(lines)
	currency = frappe.defaults.get_global_default("currency")
	return [
		{"label": _("Budget"), "value": totals["budget"], "datatype": "Currency", "currency": currency},
		{"label": _("Committed on POs"), "value": totals["committed"], "datatype": "Currency", "currency": currency},
		{"label": _("Requested"), "value": totals["requested"], "datatype": "Percent"},
		{"label": _("Ordered"), "value": totals["ordered"], "datatype": "Percent"},
		{"label": _("Received"), "value": totals["received"], "datatype": "Percent"},
		{
			"label": _("Lines fully received"),
			"value": f"{totals['lines_received']} / {totals['lines']}",
			"datatype": "Data",
		},
	]


def get_columns():
	def column(fieldname, label, fieldtype, width, options=None):
		col = {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width}
		if options:
			col["options"] = options
		return col

	return [
		column("awarded_quotation", _("Award"), "Link", 130, "Awarded Quotation"),
		column("component", _("Component"), "Data", 130),
		column("boq", _("BOQ"), "Link", 130, "BOQ"),
		column("item_code", _("Item"), "Link", 130, "Item"),
		column("item_name", _("Item Name"), "Data", 150),
		column("wbs", _("WBS"), "Link", 100, "WBS"),
		column("cost_code", _("Cost Code"), "Link", 100, "Cost Code"),
		column("uom", _("UOM"), "Link", 70, "UOM"),
		column("approved_qty", _("Approved"), "Float", 95),
		column("requested_qty", _("Requested"), "Float", 95),
		column("draft_qty", _("In Draft Requests"), "Float", 95),
		column("ordered_qty", _("Ordered"), "Float", 95),
		column("received_qty", _("Received"), "Float", 95),
		column("to_request", _("To Request"), "Float", 95),
		column("to_order", _("To Order"), "Float", 95),
		column("to_receive", _("To Receive"), "Float", 95),
		column("budget_amount", _("Budget"), "Currency", 110),
		column("committed_amount", _("Committed"), "Currency", 110),
		column("ordered_percent", _("% Ordered"), "Percent", 90),
	]
