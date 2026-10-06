# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""WBS Register - catalogue 1.2.

One row per WBS node, laid out as the tree: what the node is, where it is on
site, the BOQ line it delivers, who answers for it, its status, and the budget
allocated to it through WBS Allocation. A group's allocated budget includes
everything below it. When a filter hides a node's parents, the parents are
still shown so each row keeps its place in the tree.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	nodes = get_nodes(filters)
	if not nodes:
		return get_columns(), []

	heads = cost_heads_under(filters.cost_head) if filters.get("cost_head") else None
	matched = {n.name for n in nodes if matches(n, filters, heads)}
	by_name = {n.name: n for n in nodes}
	shown = with_ancestors(by_name, matched)
	allocated = get_allocated(nodes)
	boq_lines = get_boq_lines([n.boq_item for n in nodes if n.boq_item])

	data = []
	for node in nodes:  # ordered by lft, so parents come before children
		if node.name not in shown:
			continue
		line = boq_lines.get(node.boq_item) or {}
		data.append({
			"wbs": node.name,
			"parent_wbs": node.parent_wbs if node.parent_wbs in shown else None,
			"indent": depth(node, by_name, shown),
			"wbs_name": node.wbs_name,
			"node_type": node.node_type,
			"wbs_level": node.wbs_level,
			"project": node.project,
			"cost_head": node.cost_head,
			"location": node.location,
			"building": node.building,
			"floor": node.floor,
			"zone": node.zone,
			"boq": node.boq,
			"boq_line": " · ".join(str(v) for v in (line.get("item_code"), line.get("qty")) if v) or None,
			"responsible_person": node.responsible_person,
			"responsible_person_name": node.responsible_person_name,
			"status": node.status,
			"allocated_budget": rolled_up(node, nodes, allocated),
		})
	return get_columns(), data


def get_columns():
	text = {"align": "left"}
	return [
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 190},
		{"fieldname": "wbs_name", "label": _("WBS Name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "node_type", "label": _("Node Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "wbs_level", "label": _("Level"), "fieldtype": "Int", "width": 60},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "allocated_budget", "label": _("Allocated Budget"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "responsible_person_name", "label": _("Responsible Person"), "fieldtype": "Data", "width": 140},
		{"fieldname": "cost_head", "label": _("Cost Head"), "fieldtype": "Link", "options": "Cost Head", "width": 110, **text},
		{"fieldname": "building", "label": _("Building"), "fieldtype": "Data", "width": 150},
		{"fieldname": "floor", "label": _("Floor"), "fieldtype": "Data", "width": 130, **text},
		{"fieldname": "zone", "label": _("Zone"), "fieldtype": "Data", "width": 150, **text},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "boq", "label": _("BOQ"), "fieldtype": "Link", "options": "BOQ", "width": 130},
		{"fieldname": "boq_line", "label": _("BOQ Line"), "fieldtype": "Data", "width": 170},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
	]


def get_nodes(filters):
	conditions = {}
	if filters.get("project"):
		conditions["project"] = filters.project
	elif filters.get("company"):
		conditions["project"] = ["in", frappe.get_all("Project", filters={"company": filters.company}, pluck="name") or [""]]
	return frappe.get_all(
		"WBS",
		filters=conditions,
		fields=[
			"name", "wbs_name", "parent_wbs", "lft", "rgt", "node_type", "wbs_level", "project", "cost_head",
			"location", "building", "floor", "zone", "boq", "boq_item", "responsible_person",
			"responsible_person_name", "status",
		],
		order_by="lft",
	)


def matches(node, filters, heads):
	if filters.get("status") and node.status != filters.status:
		return False
	if heads is not None and node.cost_head not in heads:
		return False
	return True


def cost_heads_under(cost_head):
	"""The cost head and every cost head below it."""
	bounds = frappe.db.get_value("Cost Head", cost_head, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return {cost_head}
	return set(frappe.get_all("Cost Head", filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]}, pluck="name"))


def with_ancestors(by_name, matched):
	shown = set()
	for name in matched:
		while name and name not in shown:
			shown.add(name)
			name = by_name[name].parent_wbs if name in by_name else None
	return shown


def depth(node, by_name, shown):
	level, parent = 0, node.parent_wbs
	while parent in shown:
		level += 1
		parent = by_name[parent].parent_wbs
	return level


def get_allocated(nodes):
	rows = frappe.db.sql(
		"""
		select alloc.wbs as wbs, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		where alloc.docstatus < 2 and alloc.wbs in %(wbs)s
		group by alloc.wbs
		""",
		{"wbs": [n.name for n in nodes]},
		as_dict=True,
	)
	return {r.wbs: flt(r.amount) for r in rows}


def rolled_up(node, nodes, allocated):
	return sum(allocated.get(n.name, 0) for n in nodes if node.lft <= n.lft and n.rgt <= node.rgt)


def get_boq_lines(names):
	if not names:
		return {}
	rows = frappe.get_all(
		"BOQ Item", filters={"name": ["in", names], "parenttype": "BOQ"}, fields=["name", "item_code", "boq_qty", "uom"]
	)
	return {r.name: {"item_code": r.item_code, "qty": f"{flt(r.boq_qty):g} {r.uom or ''}".strip()} for r in rows}
