# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""WBS Progress - catalogue 6.6: how far each part of the job has got, in money.

Per WBS node, down the tree: its budget, % complete (budget-weighted, see
task_progress.wbs_progress), earned value (% complete × budget), % planned by
the baseline dates on the "as of" day and the value planned, and the difference:
negative is behind the baseline.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from a3_constructa.overrides.task_progress import wbs_progress


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("project"):
		return [], [], _("Choose a project to see its progress by WBS.")
	rows = wbs_progress(filters.project, filters.get("as_of") or today())
	parents = {}
	data = []
	for name, r in sorted(rows.items(), key=lambda kv: kv[1]["lft"]):
		depth = parents.get(r["parent"], -1) + 1
		parents[name] = depth
		measured = r["measured"]
		earned = flt(r["budget"] * r["percent"] / 100, 2)
		planned_value = flt(r["budget"] * r["planned"] / 100, 2)
		data.append({"wbs": name, "parent_wbs": r["parent"], "indent": depth, "wbs_name": r["wbs_name"], "budget": r["budget"],
		             "percent": r["percent"] if measured else None, "earned_value": earned if measured else None,
		             "planned": r["planned"] if measured else None, "planned_value": planned_value if measured else None,
		             "variance": flt(r["percent"] - r["planned"], 2) if measured else None,
		             "schedule_variance": flt(earned - planned_value, 2) if measured else None})
	return columns(), data, None, None, summary(data)


def columns():
	cur = {"fieldtype": "Currency", "width": 120}
	return [
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 170},
		{"fieldname": "wbs_name", "label": _("Name"), "fieldtype": "Data", "width": 210},
		{"fieldname": "budget", "label": _("Budget"), **cur},
		{"fieldname": "percent", "label": _("% Complete"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "earned_value", "label": _("Earned Value"), **cur},
		{"fieldname": "planned", "label": _("% Planned"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "planned_value", "label": _("Planned Value"), **cur},
		{"fieldname": "variance", "label": _("Variance (pts)"), "fieldtype": "Float", "precision": 1, "width": 110},
		{"fieldname": "schedule_variance", "label": _("Earned − Planned"), **cur},
	]


def summary(data):
	top = [r for r in data if r["indent"] == 0 and r["percent"] is not None]
	if not top:
		return []
	r = top[0]
	return [{"label": _("Complete"), "value": f"{r['percent']:.1f}%", "datatype": "Data", "indicator": "Blue"},
	        {"label": _("Planned by now"), "value": f"{r['planned']:.1f}%", "datatype": "Data"},
	        {"label": _("Earned value"), "value": r["earned_value"], "datatype": "Currency"},
	        {"label": _("Earned − planned"), "value": r["schedule_variance"], "datatype": "Currency",
	         "indicator": "Red" if r["schedule_variance"] < 0 else "Green"}]
