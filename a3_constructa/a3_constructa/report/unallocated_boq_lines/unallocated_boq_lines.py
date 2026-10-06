# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Unallocated BOQ Lines - catalogue 1.5.

Every line of an approved BOQ that still has something left to allocate to the
works. An item line is measured in quantity against its approved qty; an
allowance line in money against what is left of the allowance once the item
lines drawing from it are taken out. "Allocated" counts draft and submitted
allocations alike, the same as the 100% rule, so the balance is what can still
be allocated; the draft part is shown on its own because it is not yet locked.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	lines = get_lines(filters)
	held = get_allocated([l.boq_item for l in lines])

	data = []
	for l in lines:
		h = held.get(l.boq_item, {})
		if l.is_allowance:
			approved_amount = flt(l.budget_amount)
			allocated_amount = flt(h.get("amount"))
			balance_amount = approved_amount - allocated_amount
			row = {"approved_qty": None, "allocated_qty": None, "draft_qty": None, "balance_qty": None}
		else:
			approved_amount = flt(l.budget_amount)
			balance_qty = flt(l.approved_qty) - flt(h.get("qty"))
			balance_amount = balance_qty * flt(l.approved_rate)
			row = {"approved_qty": flt(l.approved_qty), "allocated_qty": flt(h.get("qty")),
			       "draft_qty": flt(h.get("draft_qty")), "balance_qty": balance_qty}
		if balance_amount <= 0.005 and not (row["balance_qty"] or 0) > 0.0005:
			continue
		row.update({
			"project": l.project,
			"cost_head": l.cost_head,
			"boq": l.boq,
			"line": f"{l.idx} · {l.description if l.is_allowance else l.item_code}",
			"line_type": _("Allowance") if l.is_allowance else _("Item"),
			"uom": None if l.is_allowance else l.uom,
			"approved_amount": approved_amount,
			"balance_amount": balance_amount,
		})
		data.append(row)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "cost_head", "label": _("Cost Head"), "fieldtype": "Link", "options": "Cost Head", "width": 110, "align": "left"},
		{"fieldname": "boq", "label": _("BOQ"), "fieldtype": "Link", "options": "BOQ", "width": 140},
		{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 260},
		{"fieldname": "line_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "balance_qty", "label": _("Balance Qty"), "fieldtype": "Float", "width": 110, "precision": 2},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Data", "width": 100},
		{"fieldname": "balance_amount", "label": _("Balance Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "approved_qty", "label": _("Approved Qty"), "fieldtype": "Float", "width": 110, "precision": 2},
		{"fieldname": "allocated_qty", "label": _("Allocated Qty"), "fieldtype": "Float", "width": 110, "precision": 2},
		{"fieldname": "draft_qty", "label": _("of which Draft"), "fieldtype": "Float", "width": 110, "precision": 2},
		{"fieldname": "approved_amount", "label": _("Approved Amount"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
	]


def get_lines(filters):
	conditions = ["boq.docstatus = 1"]
	values = {}
	if filters.get("project"):
		conditions.append("boq.project = %(project)s")
		values["project"] = filters.project
	if filters.get("company"):
		conditions.append("boq.project in (select name from `tabProject` where company = %(company)s)")
		values["company"] = filters.company
	if filters.get("cost_head"):
		bounds = frappe.db.get_value("Cost Head", filters.cost_head, ["lft", "rgt"], as_dict=True)
		if bounds:
			conditions.append("boq.cost_head in (select name from `tabCost Head` where lft >= %(lft)s and rgt <= %(rgt)s)")
			values.update(bounds)
		else:
			conditions.append("boq.cost_head = %(cost_head)s")
			values["cost_head"] = filters.cost_head
	if filters.get("boq"):
		conditions.append("boq.name = %(boq)s")
		values["boq"] = filters.boq

	return frappe.db.sql(
		"""
		select boq.name as boq, boq.project, boq.cost_head, line.name as boq_item, line.idx, line.item_code,
		       line.description, line.uom, line.is_allowance, line.approved_qty, line.approved_rate, line.budget_amount
		from `tabBOQ Item` line
		inner join `tabBOQ` boq on boq.name = line.parent and line.parenttype = 'BOQ'
		where {conditions}
		order by boq.project, boq.cost_head, boq.name, line.idx
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def get_allocated(boq_items):
	if not boq_items:
		return {}
	rows = frappe.db.sql(
		"""
		select item.boq_item, alloc.docstatus,
		       sum(item.allocated_qty) as qty, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		where item.boq_item in %(lines)s and alloc.docstatus < 2
		group by item.boq_item, alloc.docstatus
		""",
		{"lines": boq_items},
		as_dict=True,
	)
	out = {}
	for r in rows:
		e = out.setdefault(r.boq_item, {"qty": 0, "amount": 0, "draft_qty": 0})
		e["qty"] += flt(r.qty)
		e["amount"] += flt(r.amount)
		if r.docstatus == 0:
			e["draft_qty"] += flt(r.qty)
	return out
