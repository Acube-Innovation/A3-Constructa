# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Shipment TAT - build sheet head 41, row 23.

Planned against actual per milestone, so a consistently late stage shows up as a
stage rather than as a run of late shipments. The "Group By" filter gives the
averages the row asks for - by supplier, by route, by shipping line - and the
detail view lists every milestone row behind them.
"""

import frappe
from frappe import _
from frappe.utils import flt

GROUPS = {
	"Milestone": "milestone",
	"Supplier": "supplier",
	"Service Route": "service_route",
	"Shipping Line": "shipping_line",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)

	if filters.get("view") == "Detail":
		return detail_columns(), rows

	group_by = GROUPS.get(filters.get("group_by") or "Milestone", "milestone")
	return summary_columns(filters.get("group_by") or "Milestone"), summarise(rows, group_by)


def detail_columns():
	return [
		{"fieldname": "parent", "label": _("Shipment"), "fieldtype": "Link",
		 "options": "Shipment Tracking", "width": 140},
		{"fieldname": "milestone", "label": _("Milestone"), "fieldtype": "Data", "width": 200},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link",
		 "options": "Supplier", "width": 150},
		{"fieldname": "planned_date", "label": _("Planned"), "fieldtype": "Date", "width": 100},
		{"fieldname": "actual_date", "label": _("Actual"), "fieldtype": "Date", "width": 100},
		{"fieldname": "variance_days", "label": _("Variance (Days)"), "fieldtype": "Int",
		 "width": 130},
	]


def summary_columns(label):
	return [
		{"fieldname": "grouping", "label": _(label), "fieldtype": "Data", "width": 220},
		{"fieldname": "milestones", "label": _("Milestones"), "fieldtype": "Int", "width": 110},
		{"fieldname": "on_time", "label": _("On Time"), "fieldtype": "Int", "width": 100},
		{"fieldname": "late", "label": _("Late"), "fieldtype": "Int", "width": 90},
		{"fieldname": "avg_variance", "label": _("Avg Variance (Days)"),
		 "fieldtype": "Float", "precision": 1, "width": 170},
		{"fieldname": "max_variance", "label": _("Worst (Days)"), "fieldtype": "Int",
		 "width": 120},
	]


def get_rows(filters):
	conditions = ["st.docstatus < 2", "m.actual_date is not null", "m.planned_date is not null"]
	values = {}
	for f, col in (("project", "st.project"), ("supplier", "st.supplier"),
	               ("shipping_line", "st.shipping_line"), ("service_route", "st.service_route")):
		if filters.get(f):
			conditions.append("%s = %%(%s)s" % (col, f))
			values[f] = filters[f]

	return frappe.db.sql(
		"""
		select m.parent, m.milestone, m.planned_date, m.actual_date, m.variance_days,
		       st.supplier, st.service_route, st.shipping_line
		from `tabShipment Milestone` m
		inner join `tabShipment Tracking` st on st.name = m.parent
		where {conditions}
		order by m.parent, m.idx
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def summarise(rows, field):
	buckets = {}
	for r in rows:
		key = r.get(field) or _("Not Set")
		b = buckets.setdefault(key, {"grouping": key, "milestones": 0, "on_time": 0,
		                             "late": 0, "total": 0.0, "max_variance": 0})
		variance = flt(r.variance_days)
		b["milestones"] += 1
		b["total"] += variance
		# On time means on or ahead of plan, so zero counts as on time.
		if variance > 0:
			b["late"] += 1
		else:
			b["on_time"] += 1
		b["max_variance"] = max(b["max_variance"], int(variance))

	data = []
	for b in buckets.values():
		b["avg_variance"] = b["total"] / b["milestones"] if b["milestones"] else 0
		del b["total"]
		data.append(b)

	# Worst average first: that is the stage or supplier to go and fix.
	return sorted(data, key=lambda r: r["avg_variance"], reverse=True)
