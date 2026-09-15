# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Shipment Status Tracker - build sheet head 41, row 22.

One line per shipment: where it is, how long it has been there, and how long
until it reaches site. "Ageing in current status" is the number the logistics
desk actually chases - a shipment sitting twelve days in customs is the problem,
not one that has been in transit for twelve days.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate

# Terminal states: nothing is being waited on, so ageing stops meaning anything.
CLOSED_STATES = ("Received at Site", "Closed")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("Shipment"), "fieldtype": "Link",
		 "options": "Shipment Tracking", "width": 140},
		{"fieldname": "purchase_order", "label": _("PO"), "fieldtype": "Link",
		 "options": "Purchase Order", "width": 140},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link",
		 "options": "Supplier", "width": 160},
		{"fieldname": "reference_no", "label": _("Container / BL No"),
		 "fieldtype": "Data", "width": 150},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
		{"fieldname": "etd_origin", "label": _("ETD"), "fieldtype": "Date", "width": 100},
		{"fieldname": "eta_discharge", "label": _("ETA"), "fieldtype": "Date", "width": 100},
		{"fieldname": "ata_discharge", "label": _("ATA"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_site", "label": _("Days to Site"), "fieldtype": "Int",
		 "width": 110},
		{"fieldname": "ageing_days", "label": _("Ageing in Status"), "fieldtype": "Int",
		 "width": 130},
	]


def get_data(filters):
	conditions = {"docstatus": ["<", 2]}
	for f in ("project", "supplier", "status", "shipment_type"):
		if filters.get(f):
			conditions[f] = filters[f]

	rows = frappe.get_all(
		"Shipment Tracking",
		filters=conditions,
		fields=["name", "purchase_order", "supplier", "status", "bl_no",
		        "etd_origin", "eta_discharge", "ata_discharge",
		        "expected_receipt_date", "inland_arrival_date", "modified"],
		order_by="modified desc",
	)

	today = getdate(nowdate())
	data = []
	for r in rows:
		data.append({
			"name": r.name,
			"purchase_order": r.purchase_order,
			"supplier": r.supplier,
			"reference_no": r.bl_no,
			"status": r.status,
			"etd_origin": r.etd_origin,
			"eta_discharge": r.eta_discharge,
			"ata_discharge": r.ata_discharge,
			"days_to_site": days_to_site(r, today),
			"ageing_days": 0 if r.status in CLOSED_STATES
			else date_diff(today, getdate(r.modified)),
		})
	return data


def days_to_site(row, today):
	"""Days still to run before the material is on site.

	Once it has arrived inland there is nothing left to count, so the answer is
	zero rather than a negative number.
	"""
	if row.inland_arrival_date:
		return 0
	if not row.expected_receipt_date:
		return 0
	return date_diff(getdate(row.expected_receipt_date), today)
