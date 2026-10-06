# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Resource Loading - catalogue 6.3: what the programme needs, week by week.

- Labour: the peak headcount on any day of the week, by trade, and the week's
  man-days.
- Equipment: machine-days in the week, by asset category.
- Material: quantities by item, in the week they are needed by.

The figures come from the tasks' resources through
a3_constructa.overrides.task_resources.resource_loading, the helper the procurement
plan (P-05A), the equipment plan (P-08B) and the manpower histogram (P-13E) read too.
"""

import re
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate

from a3_constructa.overrides.task_resources import resource_loading


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.get("view") or "Labour"
	rows = resource_loading(project=filters.get("project"), from_date=filters.get("from_date"), to_date=filters.get("to_date"),
	                        company=filters.get("company"), resource_type=view)
	weeks = week_starts(filters)
	groups = sorted({r["group"] for r in rows})
	data, chart = build(view, rows, weeks, groups)
	return columns(view, groups, rows), data, None, chart, summary(view, data, groups)


def monday(d):
	d = getdate(d)
	return d - timedelta(days=d.weekday())


def week_starts(filters):
	start, end = monday(filters.get("from_date")), getdate(filters.get("to_date"))
	out = []
	while start <= end:
		out.append(start)
		start += timedelta(days=7)
	return out


def key(group):
	return re.sub(r"[^a-z0-9]+", "_", (group or "").lower()).strip("_")[:60] or "unassigned"


def columns(view, groups, rows):
	uoms = {}
	for r in rows:
		uoms.setdefault(r["group"], r.get("uom"))
	cols = [{"fieldname": "week", "label": _("Week of"), "fieldtype": "Date", "width": 110}]
	names = dict(frappe.get_all("Item", filters={"name": ["in", groups]}, fields=["name", "item_name"], as_list=True)) if view == "Material" else {}
	for g in groups:
		label = g if view != "Material" else f"{names.get(g) or g} ({uoms.get(g) or ''})".replace(" ()", "")
		cols.append({"fieldname": key(g), "label": label, "fieldtype": "Float", "precision": 1 if view == "Material" else 0, "width": 130})
	if view == "Labour":
		cols.append({"fieldname": "peak", "label": _("Peak headcount"), "fieldtype": "Int", "width": 120})
		cols.append({"fieldname": "man_days", "label": _("Man-days"), "fieldtype": "Float", "precision": 0, "width": 100})
	elif view == "Equipment":
		cols.append({"fieldname": "machine_days", "label": _("Machine-days"), "fieldtype": "Float", "precision": 0, "width": 110})
	return cols


def build(view, rows, weeks, groups):
	by_day = defaultdict(lambda: defaultdict(float))  # date -> group -> qty
	by_week = defaultdict(lambda: defaultdict(float))  # week -> group -> qty
	for r in rows:
		by_day[r["date"]][r["group"]] += flt(r["qty"])
		by_week[monday(r["date"])][r["group"]] += flt(r["qty"])
	data = []
	for w in weeks:
		row = {"week": w}
		days = [w + timedelta(days=i) for i in range(7)]
		if view == "Labour":
			for g in groups:
				row[key(g)] = max(by_day[d][g] for d in days)  # the most people of the trade on one day
			row["peak"] = max(sum(by_day[d].values()) for d in days)
			row["man_days"] = sum(by_week[w].values())
		else:
			for g in groups:
				row[key(g)] = by_week[w][g]
			if view == "Equipment":
				row["machine_days"] = sum(by_week[w].values())
		data.append(row)
	chart = None
	if groups and view != "Material":
		chart = {"data": {"labels": [frappe.format(w, {"fieldtype": "Date"}) for w in weeks],
		                  "datasets": [{"name": g, "values": [r[key(g)] for r in data]} for g in groups]},
		         "type": "bar", "barOptions": {"stacked": 1}, "height": 260}
	return data, chart


def summary(view, data, groups):
	if not data or not groups:
		return []
	if view == "Labour":
		return [{"label": _("Peak headcount"), "value": max(r["peak"] for r in data), "datatype": "Int", "indicator": "Blue"},
		        {"label": _("Man-days"), "value": sum(r["man_days"] for r in data), "datatype": "Float"},
		        {"label": _("Trades"), "value": len(groups), "datatype": "Int"}]
	if view == "Equipment":
		return [{"label": _("Machine-days"), "value": sum(r["machine_days"] for r in data), "datatype": "Float", "indicator": "Blue"},
		        {"label": _("Categories"), "value": len(groups), "datatype": "Int"}]
	return [{"label": _("Items needed"), "value": len(groups), "datatype": "Int", "indicator": "Blue"}]
