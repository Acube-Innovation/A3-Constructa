# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Asset Maintenance Cost - build sheet head 57, row 37.

What each machine costs to keep running: how often it broke down, how long it
was out, what the repairs cost and what the spares cost. The cost-per-hour
column is the one that decides whether to keep a machine or hire instead.

The sheet asks for "downtime hours". ERPNext's `Asset Repair.downtime` is a free
-text Data field, so it cannot be summed; hours are computed from failure_date
to completion_date instead, which is the same thing measured reliably.
"""

import frappe
from frappe import _
from frappe.utils import flt, time_diff_in_hours


def execute(filters=None):
	filters = frappe._dict(filters or {})
	repairs = get_repairs(filters)
	logs = get_maintenance_log_counts(filters)

	buckets = {}
	for r in repairs:
		b = buckets.setdefault(r.asset, {
			"asset": r.asset, "asset_name": r.asset_name,
			"asset_category": r.asset_category, "project": r.project,
			"breakdowns": 0, "downtime_hours": 0.0,
			"repair_cost": 0.0, "spare_cost": 0.0,
		})
		b["breakdowns"] += 1
		b["downtime_hours"] += downtime_hours(r)
		# total_repair_cost includes the consumed spares; repair_cost is the
		# labour and service charge on its own.
		b["repair_cost"] += flt(r.repair_cost)
		b["spare_cost"] += max(flt(r.total_repair_cost) - flt(r.repair_cost), 0)

	data = []
	for b in buckets.values():
		b["maintenance_logs"] = logs.get(b["asset"], 0)
		b["total_cost"] = b["repair_cost"] + b["spare_cost"]
		b["cost_per_hour"] = (b["total_cost"] / b["downtime_hours"]) \
			if b["downtime_hours"] else 0
		data.append(b)

	data.sort(key=lambda r: r["total_cost"], reverse=True)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset",
		 "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "asset_category", "label": _("Category"), "fieldtype": "Link",
		 "options": "Asset Category", "width": 150},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link",
		 "options": "Project", "width": 130},
		{"fieldname": "breakdowns", "label": _("Breakdowns"), "fieldtype": "Int", "width": 110},
		{"fieldname": "maintenance_logs", "label": _("Maintenance Logs"), "fieldtype": "Int",
		 "width": 140},
		{"fieldname": "downtime_hours", "label": _("Downtime (Hrs)"), "fieldtype": "Float",
		 "precision": 1, "width": 130},
		{"fieldname": "repair_cost", "label": _("Repair Cost"), "fieldtype": "Currency",
		 "width": 130},
		{"fieldname": "spare_cost", "label": _("Spare Cost"), "fieldtype": "Currency",
		 "width": 130},
		{"fieldname": "total_cost", "label": _("Total Cost"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "cost_per_hour", "label": _("Cost / Downtime Hr"),
		 "fieldtype": "Currency", "width": 150},
	]


def downtime_hours(repair):
	if not (repair.failure_date and repair.completion_date):
		return 0.0
	return max(flt(time_diff_in_hours(repair.completion_date, repair.failure_date)), 0.0)


def get_repairs(filters):
	conditions = ["ar.docstatus < 2"]
	values = {}
	if filters.get("asset"):
		conditions.append("ar.asset = %(asset)s")
		values["asset"] = filters.asset
	if filters.get("project"):
		conditions.append("ar.project = %(project)s")
		values["project"] = filters.project
	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters.asset_category
	if filters.get("from_date"):
		conditions.append("ar.failure_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("ar.failure_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		"""
		select ar.asset, ar.project, ar.failure_date, ar.completion_date,
		       ar.repair_cost, ar.total_repair_cost,
		       a.asset_name, a.asset_category
		from `tabAsset Repair` ar
		left join `tabAsset` a on a.name = ar.asset
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def get_maintenance_log_counts(filters):
	"""Planned maintenance alongside the breakdowns, for context."""
	rows = frappe.db.sql(
		"""
		select asset_name as asset, count(*) as logs
		from `tabAsset Maintenance Log`
		where docstatus < 2
		group by asset_name
		""",
		as_dict=True,
	)
	return {r.asset: r.logs for r in rows}
