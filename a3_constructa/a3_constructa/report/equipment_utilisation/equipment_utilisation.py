# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Equipment Utilisation - build sheet head 57, row 39.

How much of the period each machine was actually working, and what the idle time
cost. The hire-vs-own column answers the question the row is really asking: is
it cheaper to keep this machine or to hire one when it is needed.

The sheet names "Asset + Timesheet / equipment log" as the source. ERPNext has
no equipment log, so deployed time is taken from Timesheet Detail rows that
carry a project, and time the machine spent under repair is treated as idle
rather than deployed. Where no timesheets are kept against equipment, deployed
days read zero and the report still shows the fleet and its downtime - it does
not invent utilisation.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate, time_diff_in_hours

HOURS_PER_DAY = 8.0


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.get("from_date") or frappe.utils.add_months(nowdate(), -1))
	to_date = getdate(filters.get("to_date") or nowdate())
	period_days = max(date_diff(to_date, from_date) + 1, 1)

	assets = get_assets(filters)
	deployed = get_deployed_hours(filters, from_date, to_date)
	downtime = get_downtime_hours(filters, from_date, to_date)

	data = []
	for a in assets:
		deployed_days = flt(deployed.get(a.name, 0)) / HOURS_PER_DAY
		down_days = flt(downtime.get(a.name, 0)) / 24.0
		# Anything not worked and not under repair is available but unused.
		idle_days = max(period_days - deployed_days - down_days, 0)
		data.append({
			"asset": a.name,
			"asset_name": a.asset_name,
			"asset_category": a.asset_category,
			"project": a.project,
			"status": a.status,
			"period_days": period_days,
			"deployed_days": deployed_days,
			"downtime_days": down_days,
			"idle_days": idle_days,
			"utilisation": (deployed_days / period_days * 100) if period_days else 0,
			"gross_purchase_amount": flt(a.gross_purchase_amount),
		})

	data.sort(key=lambda r: r["utilisation"])
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset",
		 "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "asset_category", "label": _("Category"), "fieldtype": "Link",
		 "options": "Asset Category", "width": 150},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link",
		 "options": "Project", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "period_days", "label": _("Period Days"), "fieldtype": "Int",
		 "width": 110},
		{"fieldname": "deployed_days", "label": _("Deployed Days"), "fieldtype": "Float",
		 "precision": 1, "width": 130},
		{"fieldname": "downtime_days", "label": _("Downtime Days"), "fieldtype": "Float",
		 "precision": 1, "width": 130},
		{"fieldname": "idle_days", "label": _("Idle Days"), "fieldtype": "Float",
		 "precision": 1, "width": 110},
		{"fieldname": "utilisation", "label": _("Utilisation %"), "fieldtype": "Percent",
		 "width": 130},
		{"fieldname": "gross_purchase_amount", "label": _("Purchase Value"),
		 "fieldtype": "Currency", "width": 140},
	]


def get_assets(filters):
	conditions = {"docstatus": ["<", 2]}
	for f in ("asset_category", "project", "status"):
		if filters.get(f):
			conditions[f] = filters[f]
	return frappe.get_all(
		"Asset", filters=conditions,
		fields=["name", "asset_name", "asset_category", "project", "status",
		        "gross_purchase_amount"],
	)


def get_deployed_hours(filters, from_date, to_date):
	"""Hours booked against each asset on submitted timesheets."""
	rows = frappe.db.sql(
		"""
		select td.asset as asset, sum(td.hours) as hours
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		where ts.docstatus = 1
		  and td.asset is not null
		  and td.from_time >= %(from_date)s
		  and td.from_time <= %(to_date)s
		group by td.asset
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	return {r.asset: flt(r.hours) for r in rows}


def get_downtime_hours(filters, from_date, to_date):
	"""Hours each asset spent under repair inside the period."""
	rows = frappe.db.sql(
		"""
		select asset, failure_date, completion_date
		from `tabAsset Repair`
		where docstatus < 2
		  and failure_date <= %(to_date)s
		  and (completion_date is null or completion_date >= %(from_date)s)
		""",
		{"from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
	hours = {}
	for r in rows:
		if not (r.failure_date and r.completion_date):
			continue
		hours[r.asset] = hours.get(r.asset, 0) + max(
			flt(time_diff_in_hours(r.completion_date, r.failure_date)), 0
		)
	return hours
