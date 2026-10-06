# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""What of the approved BOQ budget has not yet been allocated to the works.

Catalogue 1.5: per cost head, the approved BOQ amount (allowance remaining
included, which is what an allowance line's budget_amount holds) less the
submitted WBS Allocations made from those BOQs. Budget vs WBS and Budget vs
Cost Code show it as an "Unallocated" row so their budget column adds up to the
approved BOQ.
"""

import frappe
from frappe import _
from frappe.utils import flt


def unallocated_by_cost_head(project=None, company=None):
	conditions = ["boq.docstatus = 1"]
	values = {}
	if project:
		conditions.append("boq.project = %(project)s")
		values["project"] = project
	if company:
		conditions.append("boq.project in (select name from `tabProject` where company = %(company)s)")
		values["company"] = company
	where = " and ".join(conditions)

	approved = frappe.db.sql(
		f"""
		select boq.cost_head, sum(line.budget_amount) as amount
		from `tabBOQ Item` line
		inner join `tabBOQ` boq on boq.name = line.parent and line.parenttype = 'BOQ'
		where {where}
		group by boq.cost_head
		""",
		values,
		as_dict=True,
	)
	allocated = frappe.db.sql(
		f"""
		select boq.cost_head, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		inner join `tabBOQ` boq on boq.name = alloc.boq
		where alloc.docstatus = 1 and {where}
		group by boq.cost_head
		""",
		values,
		as_dict=True,
	)
	taken = {r.cost_head: flt(r.amount) for r in allocated}
	out = {r.cost_head: flt(r.amount) - taken.get(r.cost_head, 0) for r in approved}
	names = dict(frappe.get_all("Cost Head", filters={"name": ["in", list(out) or [""]]},
	                            fields=["name", "cost_head_name"], as_list=True))
	return [
		{"cost_head": head, "cost_head_name": names.get(head) or head, "amount": amount}
		for head, amount in sorted(out.items(), key=lambda kv: kv[0] or "")
	]


def unallocated_row_label(entry):
	return _("Unallocated · {0} ({1})").format(entry["cost_head_name"], entry["cost_head"])


def wbs_subtree(wbs):
	"""The WBS node and every node below it."""
	bounds = frappe.db.get_value("WBS", wbs, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return [wbs]
	return frappe.get_all("WBS", filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]}, pluck="name")


def wbs_budget(project, wbs, cost_code=None):
	"""The current budget of a WBS node (with everything below it).

	The Budget Revision Log holds the budget where it was set: on the BOQ line's
	WBS, which is often a group such as Flooring. Submitted WBS Allocations then
	move it down to the nodes that do the work, such as WBS A. So a node's
	budget is what the log holds inside it, plus what allocations move in from
	BOQ lines outside it, less what they move out of it to nodes outside it.
	"""
	nodes = wbs_subtree(wbs)
	values = {"project": project, "nodes": nodes, "cost_code": cost_code}
	code = " and {field} = %(cost_code)s" if cost_code else ""

	logged = frappe.db.sql(
		"""select sum(amount) from `tabBudget Revision Log`
		where project = %(project)s and wbs in %(nodes)s""" + code.format(field="cost_code"),
		values,
	)[0][0]
	moved = frappe.db.sql(
		"""
		select
			sum(case when alloc.wbs in %(nodes)s and (line.wbs is null or line.wbs not in %(nodes)s)
			         then item.allocated_amount else 0 end) as moved_in,
			sum(case when line.wbs in %(nodes)s and (alloc.wbs is null or alloc.wbs not in %(nodes)s)
			         then item.allocated_amount else 0 end) as moved_out
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		left join `tabBOQ Item` line on line.name = item.boq_item
		where alloc.docstatus = 1 and alloc.project = %(project)s""" + code.format(field="item.cost_code"),
		values,
		as_dict=True,
	)[0]
	return flt(logged) + flt(moved.moved_in) - flt(moved.moved_out)


def wbs_committed_and_actual(project, wbs, cost_code=None):
	"""Committed (submitted orders not yet invoiced) and actual cost (GL and material
	issued) on a WBS node and everything below it, the same definitions Cost Code
	Wise Costing uses."""
	nodes = wbs_subtree(wbs)
	values = {"project": project, "nodes": nodes, "cost_code": cost_code}

	committed = frappe.db.sql(
		"""
		select sum(greatest(poi.base_amount - poi.billed_amt * ifnull(nullif(po.conversion_rate, 0), 1), 0))
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus = 1 and po.status not in ('Closed', 'Completed')
		  and poi.wbs in %(nodes)s""" + (" and poi.cost_code = %(cost_code)s" if cost_code else ""),
		values,
	)[0][0]
	gl = frappe.db.sql(
		"""
		select sum(gle.debit) - sum(gle.credit) from `tabGL Entry` gle
		where gle.is_cancelled = 0 and gle.wbs in %(nodes)s""" + (" and gle.cost_code = %(cost_code)s" if cost_code else ""),
		values,
	)[0][0]
	issued = frappe.db.sql(
		"""
		select sum(abs(sle.stock_value_difference))
		from `tabStock Ledger Entry` sle
		inner join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		inner join `tabStock Entry` se on se.name = sle.voucher_no
		where sle.is_cancelled = 0 and sle.voucher_type = 'Stock Entry' and sle.actual_qty < 0
		  and se.purpose = 'Material Issue' and sed.wbs in %(nodes)s""" + (" and sed.cost_code = %(cost_code)s" if cost_code else ""),
		values,
	)[0][0]
	return flt(committed), flt(gl) + flt(issued)
