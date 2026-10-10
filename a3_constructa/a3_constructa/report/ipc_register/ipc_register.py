# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""IPC Register - catalogue 4.3: every interim payment certificate raised on clients,
with what was claimed and certified, the deductions, the net due and its invoice."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{"fieldname": "name", "label": _("IPC"), "fieldtype": "Link", "options": "Client IPC", "width": 125},
		{"fieldname": "awarded_quotation", "label": _("Award"), "fieldtype": "Link", "options": "Awarded Quotation", "width": 120},
		{"fieldname": "ipc_no", "label": _("No."), "fieldtype": "Int", "width": 50},
		{"fieldname": "period_to", "label": _("Period To"), "fieldtype": "Date", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 135},
		{"fieldname": "claimed_amount", "label": _("Claimed"), **cur, "width": 115},
		{"fieldname": "certified_amount", "label": _("Certified"), **cur, "width": 115},
		{"fieldname": "retention_this_period", "label": _("Retention"), **cur, "width": 105},
		{"fieldname": "advance_recovered_this_period", "label": _("Advance Recovered"), **cur, "width": 135},
		{"fieldname": "net_due", "label": _("Net Due"), **cur, "width": 115},
		{"fieldname": "sales_invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2]}
	for field in ("company", "awarded_quotation", "status"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	return frappe.get_list("Client IPC", filters=conditions,
	                       fields=["name", "awarded_quotation", "ipc_no", "period_to", "status", "claimed_amount", "certified_amount",
	                               "retention_this_period", "advance_recovered_this_period", "net_due", "sales_invoice", "currency",
	                               "opening_invoice"],
	                       order_by="awarded_quotation asc, ipc_no asc", limit_page_length=0)


def get_summary(data):
	certified = [r for r in data if r.status in ("Certified", "Invoiced")]
	return [
		{"label": _("Certified to date"), "value": sum(flt(r.certified_amount) for r in certified), "datatype": "Currency", "indicator": "Green"},
		{"label": _("With the client"), "value": sum(flt(r.claimed_amount) for r in data if r.status == "Submitted to Client"),
		 "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Certified, not invoiced"), "value": sum(flt(r.net_due) for r in data if r.status == "Certified"),
		 "datatype": "Currency", "indicator": "Red"},
	]
