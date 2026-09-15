# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Tool Loss Analysis - build sheet head 57, row 42.

Tools lost, damaged or written off, and how much of the value was recovered from
the holder rather than absorbed. Grouped by project, site, employee or item, so
a site losing tools at twice the rate of its neighbours is visible.
"""

import frappe
from frappe import _
from frappe.utils import flt

LOSS_STATUSES = ("Lost", "Damaged", "Written Off")
# Condition on return can record a loss on an otherwise normal issue.
LOSS_CONDITIONS = ("Damaged", "Unserviceable")

GROUPS = {
	"Project": "project",
	"Site": "site",
	"Employee": "issued_to",
	"Item": "item_code",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)

	if filters.get("view") == "Detail":
		return detail_columns(), rows

	field = GROUPS.get(filters.get("group_by") or "Project", "project")
	return summary_columns(filters.get("group_by") or "Project"), summarise(rows, field)


def detail_columns():
	return [
		{"fieldname": "parent", "label": _("Tool Issue"), "fieldtype": "Link",
		 "options": "Tool Issue", "width": 140},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link",
		 "options": "Project", "width": 130},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location",
		 "width": 120},
		{"fieldname": "issued_to", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 120},
		{"fieldname": "item_code", "label": _("Tool"), "fieldtype": "Link", "options": "Item",
		 "width": 150},
		{"fieldname": "serial_no", "label": _("Serial No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "lost_qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "lost_value", "label": _("Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "recovery_amount", "label": _("Recovered"), "fieldtype": "Currency",
		 "width": 120},
		{"fieldname": "written_off", "label": _("Written Off"), "fieldtype": "Currency",
		 "width": 120},
	]


def summary_columns(label):
	return [
		{"fieldname": "grouping", "label": _(label), "fieldtype": "Data", "width": 200},
		{"fieldname": "incidents", "label": _("Incidents"), "fieldtype": "Int", "width": 100},
		{"fieldname": "lost_qty", "label": _("Qty Lost"), "fieldtype": "Float", "width": 110},
		{"fieldname": "lost_value", "label": _("Value Lost"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "recovery_amount", "label": _("Recovered"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "written_off", "label": _("Written Off"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "recovery_percent", "label": _("% Recovered"), "fieldtype": "Percent",
		 "width": 130},
	]


def get_rows(filters):
	conditions = [
		"ti.docstatus = 1",
		"(ti.status in %(loss_statuses)s or item.condition_on_return in %(loss_conditions)s)",
	]
	values = {"loss_statuses": LOSS_STATUSES, "loss_conditions": LOSS_CONDITIONS}
	for key, column in (("project", "ti.project"), ("site", "ti.site"),
	                    ("issued_to", "ti.issued_to")):
		if filters.get(key):
			conditions.append("%s = %%(%s)s" % (column, key))
			values[key] = filters[key]

	rows = frappe.db.sql(
		"""
		select ti.name as parent, ti.project, ti.site, ti.issued_to, ti.status,
		       item.item_code, item.serial_no, item.qty, item.returned_qty,
		       item.valuation_rate, item.recovery_amount
		from `tabTool Issue Item` item
		inner join `tabTool Issue` ti on ti.name = item.parent
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	for r in rows:
		# What never came back is what was lost.
		r["lost_qty"] = flt(r.qty) - flt(r.returned_qty)
		r["lost_value"] = r["lost_qty"] * flt(r.valuation_rate)
		r["recovery_amount"] = flt(r.recovery_amount)
		# Anything not recovered from the holder is absorbed by the project.
		r["written_off"] = max(r["lost_value"] - r["recovery_amount"], 0)
	return rows


def summarise(rows, field):
	buckets = {}
	for r in rows:
		key = r.get(field) or _("Not Set")
		b = buckets.setdefault(key, {"grouping": key, "incidents": 0, "lost_qty": 0.0,
		                             "lost_value": 0.0, "recovery_amount": 0.0,
		                             "written_off": 0.0})
		b["incidents"] += 1
		for f in ("lost_qty", "lost_value", "recovery_amount", "written_off"):
			b[f] += r[f]

	data = []
	for b in buckets.values():
		b["recovery_percent"] = (b["recovery_amount"] / b["lost_value"] * 100) \
			if b["lost_value"] else 0
		data.append(b)

	return sorted(data, key=lambda r: r["lost_value"], reverse=True)
