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
