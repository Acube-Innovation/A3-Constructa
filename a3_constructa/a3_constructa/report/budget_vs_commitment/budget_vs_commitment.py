# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget vs Commitment - build sheet head 26, row 17 (and row 28).

A commitment is money promised on a submitted Purchase Order but not yet
invoiced. It sits between the budget and the actual spend, which is why it
belongs next to the budget rather than in the GL reports: a project can be
inside budget on actuals and already over-committed on POs.

Budget comes from WBS Allocation, the same source as Budget vs WBS, so the two
reports agree. Commitments come from Purchase Order Item via the cost_head, wbs
and cost_code custom fields this app adds, fetched from the originating Material
Request Item.
"""

import frappe
from frappe import _
from frappe.utils import flt

GROUP_FIELDS = {"Cost Code": "cost_code", "WBS": "wbs"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by = filters.get("group_by") or "Cost Code"
	field = GROUP_FIELDS.get(group_by, "cost_code")

	budget = get_budget(filters, field)
	committed = get_committed(filters, field)

	keys = sorted(set(budget) | set(committed))
	data = []
	for key in keys:
		budgeted = flt(budget.get(key))
		commitment = flt(committed.get(key))
		data.append({
			"grouping": key,
			"budget_amount": budgeted,
			"committed_amount": commitment,
			"uncommitted": budgeted - commitment,
			"percent_committed": (commitment / budgeted * 100) if budgeted
			else (100 if commitment else 0),
		})

	return get_columns(group_by, field), data


def get_columns(group_by, field):
	return [
		{"fieldname": "grouping", "label": _(group_by), "fieldtype": "Link",
		 "options": "Cost Code" if field == "cost_code" else "WBS", "width": 180},
		{"fieldname": "budget_amount", "label": _("Budget Amount"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "committed_amount", "label": _("Committed (PO)"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "uncommitted", "label": _("Uncommitted"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "percent_committed", "label": _("% Committed"),
		 "fieldtype": "Percent", "width": 120},
	]


def get_budget(filters, field):
	# cost_code lives on the allocation row; wbs on the allocation itself.
	source = "item.cost_code" if field == "cost_code" else "alloc.wbs"
	conditions = ["alloc.docstatus < 2", "%s is not null" % source, "%s != ''" % source]
	values = {}
	if filters.get("project"):
		conditions.append("alloc.project = %(project)s")
		values["project"] = filters.project

	rows = frappe.db.sql(
		"""
		select {source} as grouping, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		where {conditions}
		group by {source}
		""".format(source=source, conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.grouping: flt(r.amount) for r in rows}


def get_committed(filters, field):
	# docstatus 1 only: a draft PO commits nothing, a cancelled one releases it.
	conditions = ["po.docstatus = 1", "poi.%s is not null" % field, "poi.%s != ''" % field]
	values = {}
	if filters.get("project"):
		conditions.append("po.project = %(project)s")
		values["project"] = filters.project
	if filters.get("company"):
		conditions.append("po.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("po.transaction_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("po.transaction_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select poi.{field} as grouping, sum(poi.base_amount) as amount
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where {conditions}
		group by poi.{field}
		""".format(field=field, conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.grouping: flt(r.amount) for r in rows}
