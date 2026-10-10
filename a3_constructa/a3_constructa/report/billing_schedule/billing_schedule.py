# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Billing Schedule - catalogue 4.2: each award's milestones as a billing plan.

One row per milestone with a billing %: when it is planned, what it bills
(billing % × the award's revised contract value), whether it is due, and the
invoice that billed it. Status reads Planned (not finished), Due (finished, not
yet invoiced), Billed (invoice raised), Paid (invoice settled), or Progress
claims (an award billed by interim certificates, where milestones only plan).
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.api.milestone_billing import bills_by_milestones, milestone_amount

STATUSES = ("Planned", "Due", "Billed", "Paid", "Progress claims")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"fieldname": "award", "label": _("Award"), "fieldtype": "Link", "options": "Awarded Quotation", "width": 120},
		{"fieldname": "milestone", "label": _("Milestone"), "fieldtype": "Data", "width": 240},
		{"fieldname": "component", "label": _("Component"), "fieldtype": "Data", "width": 150},
		{"fieldname": "planned_end", "label": _("Planned"), "fieldtype": "Date", "width": 100},
		{"fieldname": "actual_end", "label": _("Completed"), "fieldtype": "Date", "width": 100},
		{"fieldname": "billing_percent", "label": _("Billing %"), "fieldtype": "Percent", "width": 85},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "due", "label": _("Due"), "fieldtype": "Check", "width": 55},
		{"fieldname": "billed", "label": _("Billed"), "fieldtype": "Check", "width": 65},
		{"fieldname": "sales_invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"fieldname": "invoice_status", "label": _("Invoice Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2], "status": ["!=", "Cancelled"]}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("awarded_quotation"):
		conditions["name"] = filters.awarded_quotation
	data = []
	for name in frappe.get_list("Awarded Quotation", filters=conditions, pluck="name", order_by="name asc", limit_page_length=0):
		a = frappe.get_doc("Awarded Quotation", name)
		invoices = {}
		billed_names = [m.sales_invoice for m in a.milestones if m.sales_invoice]
		if billed_names and frappe.has_permission("Sales Invoice", "read"):
			invoices = {r.name: r for r in frappe.get_list("Sales Invoice", filters={"name": ["in", billed_names]},
			                                               fields=["name", "status", "docstatus"], limit_page_length=0)}
		for m in a.milestones:
			if not flt(m.billing_percent):
				continue
			inv = invoices.get(m.sales_invoice)
			if not bills_by_milestones(a):
				status = "Progress claims"
			elif m.sales_invoice:
				status = "Paid" if inv and inv.status == "Paid" else "Billed"
			elif m.actual_end:
				status = "Due"
			else:
				status = "Planned"
			if filters.get("status") and status != filters.status:
				continue
			data.append({
				"award": a.name, "milestone": m.milestone, "component": m.component, "planned_end": m.planned_end,
				"actual_end": m.actual_end, "billing_percent": m.billing_percent, "amount": milestone_amount(a, m),
				"due": int(status == "Due"), "billed": int(bool(m.sales_invoice)), "sales_invoice": m.sales_invoice,
				"invoice_status": _(inv.status) if inv else None, "status": _(status), "status_key": status, "currency": a.currency,
			})
	return data


def get_summary(data):
	def total(*statuses):
		return sum(flt(r["amount"]) for r in data if r["status_key"] in statuses)
	return [
		{"label": _("Due, not yet invoiced"), "value": total("Due"), "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Billed"), "value": total("Billed", "Paid"), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Still planned"), "value": total("Planned"), "datatype": "Currency", "indicator": "Blue"},
	]
