# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Labour Productivity - catalogue 7.5 and 13.5.

Per trade, WBS and week: quantity done, crew hours, output per man-hour, the
hours the plan allows for that quantity, and the productivity factor (planned
÷ actual hours), flagged below 0.85. See api/labour.py for each figure. The
chart follows each trade's factor week by week against the 0.85 line.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, getdate, today

from a3_constructa.api.labour import FLAG_BELOW, productivity


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.from_date = getdate(filters.get("from_date") or add_days(today(), -56))
	filters.to_date = getdate(filters.get("to_date") or today())
	rows = productivity(filters.company, filters.get("project"), filters.from_date, filters.to_date, filters.get("trade"), filters.get("wbs"))
	if frappe.utils.cint(filters.get("only_with_hours")):
		rows = [r for r in rows if r["hours"]]
	return columns(), rows, None, chart(rows), summary(rows)


def chart(rows):
	rated = [r for r in rows if r["factor"] is not None]
	if not rated:
		return None
	weeks = sorted({r["week"] for r in rated})
	trades = sorted({r["trade"] for r in rated})
	datasets = []
	for trade in trades:
		values = []
		for w in weeks:
			mine = [r for r in rated if r["trade"] == trade and r["week"] == w]
			planned, actual = sum(r["planned_hours"] for r in mine), sum(r["hours"] for r in mine)
			values.append(flt(planned / actual, 2) if actual else 0)
		datasets.append({"name": _(trade), "values": values, "chartType": "bar"})
	# Bars, so a week a trade did not work is simply empty; the flag level as a line across.
	datasets.append({"name": _("Flag line ({0})").format(FLAG_BELOW), "values": [FLAG_BELOW] * len(weeks), "chartType": "line"})
	return {"data": {"labels": [formatdate(w, "dd MMM") for w in weeks], "datasets": datasets}, "type": "axis-mixed",
	        "lineOptions": {"hideDots": 1, "regionFill": 0}, "barOptions": {"spaceRatio": 0.3}}


def summary(rows):
	rated = [r for r in rows if r["factor"] is not None]
	planned, actual = sum(r["planned_hours"] for r in rated), sum(r["hours"] for r in rated)
	factor = planned / actual if actual else None
	return [
		{"label": _("Crew hours"), "value": flt(sum(r["hours"] for r in rows), 1), "datatype": "Float"},
		{"label": _("Planned hours for the work done"), "value": flt(planned, 1), "datatype": "Float"},
		{"label": _("Productivity factor"), "value": flt(factor, 2) if factor else "–", "datatype": "Float" if factor else "Data",
		 "indicator": "Red" if factor and factor < FLAG_BELOW else "Green" if factor else "Grey"},
		{"label": _("Weeks flagged"), "value": sum(r["flag"] for r in rows), "datatype": "Int",
		 "indicator": "Red" if any(r["flag"] for r in rows) else "Green"},
	]


def columns():
	return [
		{"fieldname": "week", "label": _("Week of"), "fieldtype": "Date", "width": 100},
		{"fieldname": "trade", "label": _("Trade"), "fieldtype": "Data", "width": 120},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 110},
		{"fieldname": "tasks", "label": _("Tasks"), "fieldtype": "Data", "width": 170},
		{"fieldname": "qty", "label": _("Qty Done"), "fieldtype": "Float", "precision": 2, "width": 95},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 95},
		{"fieldname": "hours", "label": _("Crew Hours"), "fieldtype": "Float", "precision": 1, "width": 95},
		{"fieldname": "output_per_hour", "label": _("Output / Man-hour"), "fieldtype": "Float", "precision": 3, "width": 120},
		{"fieldname": "planned_hours", "label": _("Planned Hours"), "fieldtype": "Float", "precision": 1, "width": 105},
		{"fieldname": "factor", "label": _("Productivity Factor"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "source", "label": _("Planned Output From"), "fieldtype": "Data", "width": 160},
	]
