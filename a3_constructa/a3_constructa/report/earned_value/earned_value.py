# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Earned Value - catalogue 13.3.

Per project and WBS node, as of a date: BAC, PV, EV, AC, the variances SV and
CV, the indices SPI and CPI, and the forecast EAC and VAC (see
api/earned_value.py for where each figure comes from). The chart is the
S-curve: cumulative PV, EV and AC week by week (or month by month) from the
start of the work to the as-on date, for the project, or for the WBS node
chosen. An index below 1.0 is shown in red: behind the plan (SPI) or over
cost (CPI).
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, formatdate, get_last_day, getdate, today

from a3_constructa.api.earned_value import Project, figures

MONEY = ("bac", "pv", "ev", "ac", "sv", "cv", "eac", "vac")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.as_on = getdate(filters.get("as_on") or today())
	conditions = {"company": filters.company}
	if filters.get("project"):
		conditions["name"] = filters.project
	if filters.get("wbs"):
		conditions["name"] = frappe.db.get_value("WBS", filters.wbs, "project")
	projects = frappe.get_list("Project", filters=conditions, fields=["name", "project_name"], order_by="name")
	if not projects:
		return columns(), [], _("No projects for these filters.")

	loaded = {p.name: Project(p.name) for p in projects}
	rows = []
	for p in projects:
		ev = loaded[p.name]
		if not ev.nodes and not ev.costs:
			continue
		rows += project_rows(p, ev, ev.on(filters.as_on), filters.get("wbs"))
	scope = scope_label(filters, projects)
	chart = s_curve(loaded, filters)
	total = chart.pop("_total")
	return columns(), rows, None, chart, summary(total, scope)


def project_rows(p, ev, on, wbs=None):
	rows = []
	keep = set(ev.nodes)
	if wbs:
		root = ev.nodes[wbs]
		keep = {n for n, w in ev.nodes.items() if root.lft <= w.lft and w.rgt <= root.rgt}
	else:
		rows.append({"key": p.name, "parent_key": None, "indent": 0, "level": "Project", "project": p.name,
		             "label": f"{p.name}: {p.project_name}", **on[""]})
	depth = {}
	for name, node in ev.nodes.items():  # in lft order
		if name not in keep:
			continue
		parent = node.parent_wbs if node.parent_wbs in keep else None
		depth[name] = depth[parent] + 1 if parent else (0 if wbs else 1)
		rows.append({"key": f"{p.name}|{name}", "parent_key": f"{p.name}|{parent}" if parent else (None if wbs else p.name),
		             "indent": depth[name], "level": "WBS", "project": p.name, "wbs": name,
		             "label": f"{name}: {node.wbs_name}", **on[name]})
	if not wbs and abs(on[""]["no_wbs_ac"]) >= 0.005:
		rows.append({"key": f"{p.name}|", "parent_key": p.name, "indent": 1, "level": "No WBS", "project": p.name,
		             "label": _("Cost with no WBS"), **dict.fromkeys(("bac", "planned", "pv", "percent", "ev", "sv", "cv", "spi", "cpi", "eac", "vac")),
		             "ac": on[""]["no_wbs_ac"]})  # cost only: nothing to plan or earn here
	return rows


def scope_label(filters, projects):
	if filters.get("wbs"):
		return f"{filters.wbs}: {frappe.db.get_value('WBS', filters.wbs, 'wbs_name')}"
	if len(projects) == 1:
		return f"{projects[0].name}: {projects[0].project_name}"
	return _("All projects of {0}").format(filters.company)


def period_ends(start, end, period):
	"""The dates the S-curve is read on: each week (or month) end from the start, and the as-on date."""
	days = []
	day = add_days(start, 6) if period != "Monthly" else get_last_day(start)
	while getdate(day) < getdate(end):
		days.append(getdate(day))
		day = add_days(day, 7) if period != "Monthly" else get_last_day(add_months(day, 1))
	days.append(getdate(end))
	return days


def s_curve(loaded, filters):
	wanted = [ev for ev in loaded.values() if ev.nodes or ev.costs]
	key = filters.get("wbs") or ""
	start = min((ev.first_day() for ev in wanted), default=filters.as_on)
	labels, pv, ev_, ac = [], [], [], []
	total = None
	for day in period_ends(start, filters.as_on, filters.get("period") or "Weekly"):
		sums = dict.fromkeys(("bac", "pv", "ev", "ac"), 0.0)
		for ev in wanted:
			if key and key not in ev.nodes:
				continue
			f = ev.on(day)[key]
			for k in sums:
				sums[k] += flt(f[k])
		labels.append(formatdate(day, "dd MMM"))
		pv.append(flt(sums["pv"], 2))
		ev_.append(flt(sums["ev"], 2))
		ac.append(flt(sums["ac"], 2))
		total = sums
	bac = total["bac"]
	return {
		"data": {"labels": labels, "datasets": [{"name": _("Planned value (PV)"), "values": pv},
		                                        {"name": _("Earned value (EV)"), "values": ev_},
		                                        {"name": _("Actual cost (AC)"), "values": ac}]},
		"type": "line", "colors": ["#7c8db5", "#2e9e6a", "#d1603d"], "lineOptions": {"regionFill": 0, "hideDots": 1},
		"axisOptions": {"xIsSeries": 1}, "fieldtype": "Currency",
		"_total": figures(bac, total["pv"] / bac * 100 if bac else 0, total["ev"] / bac * 100 if bac else 0, total["ac"]),
	}


def summary(t, scope):
	def ratio(v):
		return {"value": flt(v, 2) if v is not None else "–", "indicator": "Red" if v is not None and v < 1 else "Green" if v is not None else "Grey"}
	return [
		{"label": _("Scope"), "value": scope, "datatype": "Data", "indicator": "Blue"},
		{"label": _("BAC"), "value": t["bac"], "datatype": "Currency"},
		{"label": _("PV"), "value": t["pv"], "datatype": "Currency"},
		{"label": _("EV"), "value": t["ev"], "datatype": "Currency"},
		{"label": _("AC"), "value": t["ac"], "datatype": "Currency"},
		{"label": _("SPI"), "datatype": "Float", **ratio(t["spi"])},
		{"label": _("CPI"), "datatype": "Float", **ratio(t["cpi"])},
		{"label": _("EAC"), "value": t["eac"] if t["eac"] is not None else "–", "datatype": "Currency" if t["eac"] is not None else "Data"},
	]


def columns():
	cur = lambda name, label, width=115: {"fieldname": name, "label": label, "fieldtype": "Currency", "width": width}
	pct = lambda name, label: {"fieldname": name, "label": label, "fieldtype": "Percent", "width": 95}
	idx = lambda name, label: {"fieldname": name, "label": label, "fieldtype": "Float", "precision": 2, "width": 70}
	return [
		{"fieldname": "label", "label": _("Project / WBS"), "fieldtype": "Data", "width": 280},
		cur("bac", _("BAC")), pct("planned", _("Planned %")), cur("pv", _("PV")), pct("percent", _("Complete %")),
		cur("ev", _("EV")), cur("ac", _("AC")), cur("sv", _("SV")), cur("cv", _("CV")), idx("spi", _("SPI")), idx("cpi", _("CPI")),
		cur("eac", _("EAC"), 120), cur("vac", _("VAC")),
	]
