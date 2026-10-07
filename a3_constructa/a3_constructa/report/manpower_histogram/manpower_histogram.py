# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Manpower Histogram - catalogue 7.6 and 13.5.

Headcount per trade per week: planned (the labour on the tasks' resources,
P-06B) against actual (workers present on the project, plus subcontractors'
headcount from the Daily Site Reports), each the busiest day of the week. A
week is a tree row with its trades below it; the chart stacks nothing and
compares the weeks' totals side by side.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, getdate, today

from a3_constructa.api.labour import headcount


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.from_date = getdate(filters.get("from_date") or add_days(today(), -42))
	filters.to_date = getdate(filters.get("to_date") or add_days(today(), 28))
	weeks = headcount(filters.company, filters.get("project"), filters.from_date, filters.to_date, filters.get("trade"))
	rows, totals = [], []
	for week in sorted({w for w, _t in weeks}):
		trades = sorted(t for w, t in weeks if w == week)
		kids = [{"key": f"{week}|{t}", "parent_key": str(week), "indent": 1, "label": _(t), "week": week, "trade": t, **weeks[(week, t)]} for t in trades]
		for k in kids:
			k["difference"] = k["actual"] - k["planned"]
		total = {f: sum(k[f] for k in kids) for f in ("planned", "actual", "own", "subcontract")}
		total["difference"] = total["actual"] - total["planned"]
		rows.append({"key": str(week), "parent_key": None, "indent": 0, "label": _("Week of {0}").format(formatdate(week, "dd MMM yyyy")),
		             "week": week, **total})
		rows += kids
		totals.append((week, total))
	return columns(), rows, None, chart(totals, filters), summary(totals)


def chart(totals, filters):
	if not totals:
		return None
	return {"data": {"labels": [formatdate(w, "dd MMM") for w, _t in totals],
	                 "datasets": [{"name": _("Planned"), "values": [t["planned"] for _w, t in totals]},
	                              {"name": _("Actual"), "values": [t["actual"] for _w, t in totals]}]},
	        "type": "bar", "colors": ["#9aa9c9", "#2e7d5b"], "barOptions": {"spaceRatio": 0.4}}


def summary(totals):
	past = [t for w, t in totals if w <= getdate(today())]
	peak_planned = max((t["planned"] for _w, t in totals), default=0)
	peak_actual = max((t["actual"] for _w, t in totals), default=0)
	short = sum(1 for t in past if t["actual"] < t["planned"])
	return [
		{"label": _("Peak planned"), "value": peak_planned, "datatype": "Float"},
		{"label": _("Peak on site"), "value": peak_actual, "datatype": "Float"},
		{"label": _("Weeks short of plan"), "value": short, "datatype": "Int", "indicator": "Orange" if short else "Green"},
	]


def columns():
	n = lambda name, label, width=110: {"fieldname": name, "label": label, "fieldtype": "Int", "width": width}
	return [
		{"fieldname": "label", "label": _("Week / Trade"), "fieldtype": "Data", "width": 220},
		n("planned", _("Planned")), n("actual", _("Actual")), n("difference", _("Actual − Planned"), 130),
		n("own", _("Own workers")), n("subcontract", _("Subcontractors"), 120),
	]
