# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demurrage & Detention - build sheet head 41, row 24.

Demurrage and detention are avoidable costs, so the point of this report is to
attribute them: which shipping line, which project, and how far past the free
days the container actually ran. Free days come from the Freight Rate Contract
for the shipping line and route, which is the only place they are recorded.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	free_days = get_free_days()

	data = []
	for r in rows:
		free = free_days.get((r.shipping_line, r.service_route))
		data.append({
			"name": r.name,
			"project": r.project,
			"shipping_line": r.shipping_line,
			"service_route": r.service_route,
			"ata_discharge": r.ata_discharge,
			"free_days": free,
			"container_return_date": r.container_return_date,
			"days_held": days_held(r),
			"demurrage_days": r.demurrage_days,
			"demurrage_amount": flt(r.demurrage_amount),
			"detention_amount": flt(r.detention_amount),
			"total_cost": flt(r.demurrage_amount) + flt(r.detention_amount),
		})

	# Most expensive first - that is the conversation to have with the line.
	data.sort(key=lambda r: r["total_cost"], reverse=True)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "name", "label": _("Shipment"), "fieldtype": "Link",
		 "options": "Shipment Tracking", "width": 130},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link",
		 "options": "Project", "width": 130},
		{"fieldname": "shipping_line", "label": _("Shipping Line"), "fieldtype": "Link",
		 "options": "Supplier", "width": 150},
		{"fieldname": "service_route", "label": _("Route"), "fieldtype": "Link",
		 "options": "Service Route", "width": 140},
		{"fieldname": "ata_discharge", "label": _("Arrived"), "fieldtype": "Date", "width": 100},
		{"fieldname": "container_return_date", "label": _("Returned"), "fieldtype": "Date",
		 "width": 100},
		{"fieldname": "free_days", "label": _("Free Days"), "fieldtype": "Int", "width": 100},
		{"fieldname": "days_held", "label": _("Days Held"), "fieldtype": "Int", "width": 100},
		{"fieldname": "demurrage_days", "label": _("Demurrage Days"), "fieldtype": "Int",
		 "width": 130},
		{"fieldname": "demurrage_amount", "label": _("Demurrage"), "fieldtype": "Currency",
		 "width": 130},
		{"fieldname": "detention_amount", "label": _("Detention"), "fieldtype": "Currency",
		 "width": 130},
		{"fieldname": "total_cost", "label": _("Total"), "fieldtype": "Currency", "width": 130},
	]


def get_rows(filters):
	conditions = {"docstatus": ["<", 2], "shipment_type": "Import"}
	for f in ("project", "shipping_line", "service_route"):
		if filters.get(f):
			conditions[f] = filters[f]
	if filters.get("only_with_cost"):
		conditions["demurrage_amount"] = [">", 0]

	return frappe.get_all(
		"Shipment Tracking",
		filters=conditions,
		fields=["name", "project", "shipping_line", "service_route", "ata_discharge",
		        "container_return_date", "demurrage_days", "demurrage_amount",
		        "detention_amount"],
	)


def days_held(row):
	"""Calendar days the container was held, arrival to return."""
	if not (row.ata_discharge and row.container_return_date):
		return 0
	return date_diff(row.container_return_date, row.ata_discharge)


def get_free_days():
	"""Free days per (shipping line, route), from the active rate contracts."""
	contracts = frappe.get_all(
		"Freight Rate Contract",
		filters={"docstatus": ["<", 2]},
		fields=["supplier", "service_route", "free_days", "valid_from"],
		order_by="valid_from desc",
	)
	# Newest contract wins, which is why the query is ordered and the first
	# value for a pair is kept.
	free = {}
	for c in contracts:
		free.setdefault((c.supplier, c.service_route), c.free_days)
	return free
