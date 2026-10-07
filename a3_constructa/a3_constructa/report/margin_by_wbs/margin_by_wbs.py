# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Margin by WBS - catalogue 13.4.

Per project and WBS node, up to a date: the revenue the client has certified
(Client IPC lines; for a job billed by milestones, its invoices - see
api/revenue.py), the actual cost (ledger and material issued, as the Job Cost
Report), the margin and the margin %. A node includes everything below it.
Revenue or cost with no WBS (materials on site, freight) shows on its own row
under the project, so the project row is the sum of what is shown.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from a3_constructa.api.earned_value import Project
from a3_constructa.api.revenue import certified_revenue, invoiced_revenue


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.as_on = getdate(filters.get("as_on") or today())
	conditions = {"company": filters.company}
	if filters.get("project"):
		conditions["name"] = filters.project
	projects = frappe.get_list("Project", filters=conditions, fields=["name", "project_name"], order_by="name")
	rows = []
	for p in projects:
		rows += project_rows(p, filters.as_on)
	if frappe.utils.cint(filters.get("hide_zero")):
		rows = [r for r in rows if abs(flt(r.get("revenue"))) >= 0.005 or abs(flt(r.get("cost"))) >= 0.005]
	totals = [r for r in rows if r["level"] == "Project"]
	return columns(), rows, None, None, summary(totals)


def project_rows(p, as_on):
	ev = Project(p.name)
	certified, _ipcs = certified_revenue(p.name, as_on)
	invoiced = invoiced_revenue(p.name, as_on)
	if not ev.nodes and not ev.costs and not certified and not invoiced:
		return []
	own_cost = {n: ev.actual_on(n, as_on) for n in ev.nodes}

	def subtree(name):
		node = ev.nodes[name]
		return [n for n, w in ev.nodes.items() if node.lft <= w.lft and w.rgt <= node.rgt]

	out, depth = [], {}
	for name, node in ev.nodes.items():
		names = subtree(name)
		parent = node.parent_wbs if node.parent_wbs in ev.nodes else None
		depth[name] = depth[parent] + 1 if parent else 1
		out.append(line(f"{p.name}|{name}", f"{p.name}|{parent}" if parent else p.name, depth[name], "WBS", p.name, name,
		                f"{name}: {node.wbs_name}", sum(certified.get(n, 0) for n in names), sum(invoiced.get(n, 0) for n in names),
		                sum(own_cost[n] for n in names)))
	stray = {w for w in list(certified) + list(invoiced) if w and w not in ev.nodes}  # a WBS of another project
	none_rev_c = certified.get(None, 0) + sum(certified[w] for w in stray if w in certified)
	none_rev_i = invoiced.get(None, 0) + sum(invoiced[w] for w in stray if w in invoiced)
	none_cost = ev.actual_on(None, as_on)
	if abs(none_rev_c) + abs(none_rev_i) + abs(none_cost) >= 0.005:
		out.append(line(f"{p.name}|", p.name, 1, "No WBS", p.name, None, _("No WBS (materials on site, freight and the like)"),
		                none_rev_c, none_rev_i, none_cost))
	roots = [r for r in out if r["parent_key"] == p.name]
	total = line(p.name, None, 0, "Project", p.name, None, f"{p.name}: {p.project_name}", sum(r["certified"] for r in roots),
	             sum(r["invoiced"] for r in roots), sum(r["cost"] for r in roots))
	return [total] + out


def line(key, parent, indent, level, project, wbs, label, certified, invoiced, cost):
	revenue = certified + invoiced
	margin = revenue - cost
	return {"key": key, "parent_key": parent, "indent": indent, "level": level, "project": project, "wbs": wbs, "label": label,
	        "certified": certified, "invoiced": invoiced, "revenue": revenue, "cost": cost, "margin": margin,
	        "margin_percent": margin / revenue * 100 if revenue else None}


def summary(totals):
	revenue = sum(r["revenue"] for r in totals)
	cost = sum(r["cost"] for r in totals)
	margin = revenue - cost
	return [
		{"label": _("Revenue"), "value": revenue, "datatype": "Currency"},
		{"label": _("Actual cost"), "value": cost, "datatype": "Currency"},
		{"label": _("Margin"), "value": margin, "datatype": "Currency", "indicator": "Green" if margin >= 0 else "Red"},
		{"label": _("Margin %"), "value": flt(margin / revenue * 100, 1) if revenue else "–", "datatype": "Percent" if revenue else "Data",
		 "indicator": "Green" if margin >= 0 else "Red"},
	]


def columns():
	cur = lambda name, label, width=130: {"fieldname": name, "label": label, "fieldtype": "Currency", "width": width}
	return [
		{"fieldname": "label", "label": _("Project / WBS"), "fieldtype": "Data", "width": 320},
		cur("certified", _("Certified (IPC)")), cur("invoiced", _("Billed by milestone")), cur("revenue", _("Revenue")),
		cur("cost", _("Actual cost")), cur("margin", _("Margin")),
		{"fieldname": "margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 100},
	]
