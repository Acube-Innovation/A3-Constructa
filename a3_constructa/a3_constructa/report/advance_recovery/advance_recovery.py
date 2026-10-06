# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Advance Recovery - catalogue 4.4: per award, the advance billed against the
client's bank guarantee, what the IPCs have recovered, and what is left, with
the guarantee and its expiry (it can be reduced as the advance is recovered)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{"fieldname": "award", "label": _("Award"), "fieldtype": "Link", "options": "Awarded Quotation", "width": 120},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 220},
		{"fieldname": "advance_percent", "label": _("Advance %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "recovery_percent", "label": _("Recovery %"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "advance_billed", "label": _("Advance Billed"), **cur, "width": 130},
		{"fieldname": "recovered", "label": _("Recovered"), **cur, "width": 120},
		{"fieldname": "balance", "label": _("Still to Recover"), **cur, "width": 130},
		{"fieldname": "recovered_percent", "label": _("Recovered %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "bank_guarantee", "label": _("Bank Guarantee"), "fieldtype": "Link", "options": "Bank Guarantee", "width": 130},
		{"fieldname": "guarantee_expiry", "label": _("Guarantee Expiry"), "fieldtype": "Date", "width": 120},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2], "status": ["!=", "Cancelled"]}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("awarded_quotation"):
		conditions["name"] = filters.awarded_quotation
	data = []
	for a in frappe.get_list("Awarded Quotation", filters=conditions, fields=["name", "title", "advance_percent", "advance_recovery_percent", "currency"],
	                         order_by="name asc", limit_page_length=0):
		invoices = frappe.get_all("Sales Invoice", filters={"awarded_quotation": a.name, "docstatus": 1, "is_advance_invoice": 1},
		                          fields=["net_total", "bank_guarantee"], order_by="posting_date asc")
		billed = sum(flt(i.net_total) for i in invoices)
		if not billed and not flt(a.advance_percent):
			continue
		recovered = flt(frappe.db.sql("""select sum(advance_recovered_this_period) from `tabClient IPC`
			where awarded_quotation = %s and docstatus = 1""", a.name)[0][0])
		bg = invoices[-1].bank_guarantee if invoices else None
		expiry = frappe.db.get_value("Bank Guarantee", bg, "end_date") if bg else None
		data.append({"award": a.name, "title": a.title, "advance_percent": a.advance_percent, "recovery_percent": a.advance_recovery_percent,
		             "advance_billed": billed, "recovered": recovered, "balance": billed - recovered,
		             "recovered_percent": recovered / billed * 100 if billed else None, "bank_guarantee": bg, "guarantee_expiry": expiry,
		             "expired": int(bool(expiry and getdate(expiry) < getdate(today()) and billed - recovered > 0.005)), "currency": a.currency})
	return data


def get_summary(data):
	return [
		{"label": _("Advances billed"), "value": sum(r["advance_billed"] for r in data), "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Recovered"), "value": sum(r["recovered"] for r in data), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Still to recover"), "value": sum(r["balance"] for r in data), "datatype": "Currency", "indicator": "Orange"},
	]
