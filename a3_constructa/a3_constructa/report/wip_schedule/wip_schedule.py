# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""WIP Schedule - catalogue 13.4: each award's work in progress, on a date.

Per awarded contract:
- revised contract value (with approved variations);
- % complete: the project's WBS-weighted % complete on the date (the earned
  value roll-up, EV ÷ BAC); with no budget on the WBS yet, the roll-up's
  average of the tasks; an award with no project yet, its own Progress %; a
  Completed award, 100%. The report says which it used;
- earned revenue = % complete × revised contract value;
- billed to date: invoices to the client on the award, net of tax, without
  advance invoices or retention releases (api/revenue.py);
- over / (under) billing = billed − earned: billed ahead of the work is a
  liability, billed behind it is revenue still to invoice;
- cost to date: actual cost of the project (as the Job Cost Report, to the date);
- forecast cost: the Job Cost Report's forecast at completion (actual +
  committed + cost to complete);
- gross profit recognised = (revised contract value − forecast cost) × %
  complete; a contract forecast to lose money recognises the whole loss at once.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from a3_constructa.api.earned_value import Project
from a3_constructa.api.revenue import billed_to_date
from a3_constructa.a3_constructa.report.job_cost_report import job_cost_report


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.as_on = getdate(filters.get("as_on") or today())
	conditions = {"company": filters.company, "status": ["!=", "Cancelled"], "docstatus": ["<", 2]}
	if filters.get("awarded_quotation"):
		conditions["name"] = filters.awarded_quotation
	if filters.get("project"):
		conditions["project"] = filters.project
	awards = frappe.get_list("Awarded Quotation", filters=conditions, order_by="award_date",
	                         fields=["name", "title", "project", "customer", "status", "revised_contract_value", "progress_percent", "award_date"])
	rows = [row(a, filters) for a in awards if not a.award_date or getdate(a.award_date) <= filters.as_on]
	return columns(), rows, None, None, summary(rows)


def row(a, filters):
	value = flt(a.revised_contract_value)
	if a.project:
		project = Project(a.project)
		on = project.on(filters.as_on)
		ev = on[""]
		roots = [n for n, w in project.nodes.items() if w.parent_wbs not in project.nodes]
		if ev["bac"]:
			percent, source = ev["percent"], _("WBS progress")
		elif roots:
			# No budget on the WBS yet: the roll-up averages the tasks themselves.
			percent, source = sum(on[n]["percent"] for n in roots) / len(roots), _("Task progress (no WBS budget)")
		else:
			percent, source = flt(a.progress_percent), _("Award's progress")
		cost = ev["ac"]
		jc = job_cost_report.execute({"company": filters.company, "project": a.project, "as_on": filters.as_on})[1]
		forecast = next((r["forecast"] for r in jc if r["level"] == "Project"), cost)
	else:
		percent, source, cost, forecast = flt(a.progress_percent), _("Award's progress (no project yet)"), 0.0, 0.0
	if a.status == "Completed":
		percent, source = 100.0, _("Completed")
	earned = value * percent / 100
	billed = billed_to_date(a.name, filters.as_on)
	profit = value - forecast if forecast else None
	if profit is None:
		recognised = None
	else:
		recognised = profit if profit < 0 else profit * percent / 100
	return {"awarded_quotation": a.name, "title": a.title, "project": a.project, "customer": a.customer, "status": a.status,
	        "contract_value": value, "percent": percent, "percent_source": source, "earned": earned, "billed": billed,
	        "over_under": billed - earned, "cost": cost, "forecast_cost": forecast or None, "forecast_profit": profit,
	        "recognised": recognised}


def summary(rows):
	over = sum(r["over_under"] for r in rows if r["over_under"] > 0)
	under = -sum(r["over_under"] for r in rows if r["over_under"] < 0)
	return [
		{"label": _("Earned revenue"), "value": sum(r["earned"] for r in rows), "datatype": "Currency"},
		{"label": _("Billed to date"), "value": sum(r["billed"] for r in rows), "datatype": "Currency"},
		{"label": _("Over-billed"), "value": over, "datatype": "Currency", "indicator": "Orange" if over else "Green"},
		{"label": _("Under-billed"), "value": under, "datatype": "Currency", "indicator": "Blue" if under else "Green"},
		{"label": _("Gross profit recognised"), "value": sum(flt(r["recognised"]) for r in rows), "datatype": "Currency"},
	]


def columns():
	cur = lambda name, label, width=125: {"fieldname": name, "label": label, "fieldtype": "Currency", "width": width}
	return [
		{"fieldname": "awarded_quotation", "label": _("Award"), "fieldtype": "Link", "options": "Awarded Quotation", "width": 120},
		{"fieldname": "title", "label": _("Contract"), "fieldtype": "Data", "width": 220},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		cur("contract_value", _("Revised Contract Value"), 140),
		{"fieldname": "percent", "label": _("% Complete"), "fieldtype": "Percent", "width": 100},
		cur("earned", _("Earned Revenue")), cur("billed", _("Billed to Date")), cur("over_under", _("Over / (Under) Billed"), 140),
		cur("cost", _("Cost to Date")), cur("forecast_cost", _("Forecast Cost")), cur("forecast_profit", _("Forecast Profit")),
		cur("recognised", _("GP Recognised"), 130),
		{"fieldname": "percent_source", "label": _("% Complete From"), "fieldtype": "Data", "width": 170},
	]
