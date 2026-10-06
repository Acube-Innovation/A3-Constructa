# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Variation Register - catalogue 3.5: every variation order of every award.

One row per variation order: its award, type, status, amount and days, the WBS
nodes its lines sit on, the change event it came from, and when it was raised,
sent to the client and approved. The summary splits the value into approved
(on the contract and the budget) and still with the client.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Variation Order"), "fieldtype": "Link", "options": "Variation Order", "width": 125},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 230},
		{"fieldname": "awarded_quotation", "label": _("Award"), "fieldtype": "Link", "options": "Awarded Quotation", "width": 120},
		{"fieldname": "variation_type", "label": _("Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 135},
		{"fieldname": "total_amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "time_extension_days", "label": _("Days"), "fieldtype": "Int", "width": 65},
		{"fieldname": "wbs_lines", "label": _("WBS Lines"), "fieldtype": "Data", "width": 170},
		{"fieldname": "change_event", "label": _("Change Event"), "fieldtype": "Link", "options": "Change Event", "width": 120},
		{"fieldname": "vo_date", "label": _("Raised"), "fieldtype": "Date", "width": 95},
		{"fieldname": "submitted_date", "label": _("Submitted"), "fieldtype": "Date", "width": 95},
		{"fieldname": "approved_date", "label": _("Approved"), "fieldtype": "Date", "width": 95},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	conditions = {}
	if filters.get("company"):
		conditions["awarded_quotation"] = ["in", frappe.get_list("Awarded Quotation", filters={"company": filters.company}, pluck="name") or [""]]
	if filters.get("awarded_quotation"):
		conditions["awarded_quotation"] = filters.awarded_quotation
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("variation_type"):
		conditions["variation_type"] = filters.variation_type
	rows = frappe.get_list(
		"Variation Order",
		filters=conditions,
		fields=["name", "subject", "awarded_quotation", "variation_type", "status", "total_amount", "time_extension_days",
		        "change_event", "vo_date", "submitted_date", "approved_date", "currency"],
		order_by="vo_date desc, name desc",
		limit_page_length=0,
	)
	lines = {}
	for r in frappe.get_all("Variation Order Item", filters={"parent": ["in", [r.name for r in rows] or [""]], "parenttype": "Variation Order"},
	                        fields=["parent", "wbs"], order_by="idx"):
		lines.setdefault(r.parent, [])
		label = r.wbs or _("no WBS")
		if label not in lines[r.parent]:
			lines[r.parent].append(label)
	for r in rows:
		r.wbs_lines = ", ".join(lines.get(r.name, []))
		r.status_label = _(r.status)
	return rows


def get_summary(rows):
	def total(statuses):
		return sum(flt(r.total_amount) for r in rows if r.status in statuses)
	return [
		{"label": _("Approved"), "value": total(("Approved",)), "datatype": "Currency", "indicator": "Green"},
		{"label": _("With the client"), "value": total(("Submitted to Client",)), "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Draft"), "value": total(("Draft",)), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Approved days"), "value": sum(r.time_extension_days or 0 for r in rows if r.status == "Approved"), "datatype": "Int",
		 "indicator": "Green"},
	]
