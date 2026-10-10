# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget vs Cost Code - build sheet head 20, row 14.

The same comparison as Budget vs WBS, grouped one level down: cost_code sits on
the WBS Allocation Item row rather than on the parent, so the budget side groups
by the child field. Actuals come from GL Entry via the `cost_code` custom field
this app adds, and read zero until the spending workspaces stamp it. Budget
counts submitted allocations; the approved BOQ budget not yet allocated shows
as one "Unallocated" row per cost head.

Since P-03B the budget is shown as original (allocated), the variations and
transfers made since (Budget Revision Log), and the revised budget; variance and
% utilised are against the revised budget.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.api.budget_allocation import budget_changes, unallocated_by_cost_head, unallocated_row_label


def execute(filters=None):
	filters = frappe._dict(filters or {})
	budget = get_budget(filters)
	changes = budget_changes("cost_code", filters.get("project"), filters.get("company"), filters.get("cost_code"))
	actual = get_actual(filters)

	codes = sorted((set(budget) | set(actual) | set(changes)) - {None})
	descriptions = get_descriptions(codes)

	data = [row(code, descriptions.get(code), budget.get(code), changes.get(code), actual.get(code)) for code in codes]
	if changes.get(None) and not filters.get("cost_code"):
		data.append(row(None, _("Variations and transfers not on a cost code"), 0, changes[None], 0))

	if not filters.get("cost_code"):
		for entry in unallocated_by_cost_head(filters.get("project"), filters.get("company")):
			data.append({
				"cost_code": None,
				"description": unallocated_row_label(entry),
				"original_budget": entry["amount"],
				"budget_changes": 0,
				"budget_amount": entry["amount"],
				"actual_amount": 0,
				"variance": entry["amount"],
				"percent_utilised": 0,
				"is_unallocated": 1,
			})

	return get_columns(), data


def row(code, description, original, change, spent):
	original, change, spent = flt(original), flt(change), flt(spent)
	revised = original + change
	return {
		"cost_code": code,
		"description": description,
		"original_budget": original,
		"budget_changes": change,
		"budget_amount": revised,
		"actual_amount": spent,
		"variance": revised - spent,
		"percent_utilised": (spent / revised * 100) if revised else (100 if spent else 0),
	}


def get_columns():
	return [
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 160},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 320},
		{"fieldname": "original_budget", "label": _("Original Budget"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "budget_changes", "label": _("Variations & Transfers"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "budget_amount", "label": _("Revised Budget"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "actual_amount", "label": _("Actual Amount"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "percent_utilised", "label": _("% Utilised"),
		 "fieldtype": "Percent", "width": 110},
	]


def get_budget(filters):
	conditions = ["alloc.docstatus = 1", "item.cost_code is not null", "item.cost_code != ''"]
	values = {}
	if filters.get("project"):
		conditions.append("alloc.project = %(project)s")
		values["project"] = filters.project
	if filters.get("cost_code"):
		conditions.append("item.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code

	rows = frappe.db.sql(
		"""
		select item.cost_code as cost_code, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		where {conditions}
		group by item.cost_code
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.cost_code: flt(r.amount) for r in rows}


def get_actual(filters):
	conditions = ["gle.is_cancelled = 0", "gle.cost_code is not null", "gle.cost_code != ''"]
	values = {}
	if filters.get("project"):
		conditions.append("gle.project = %(project)s")
		values["project"] = filters.project
	if filters.get("cost_code"):
		conditions.append("gle.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code
	if filters.get("company"):
		conditions.append("gle.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("gle.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("gle.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select gle.cost_code as cost_code, sum(gle.debit) - sum(gle.credit) as amount
		from `tabGL Entry` gle
		-- Cost only: since P-01D the WBS and cost code are on every GL row a line
		-- makes, including stock and Stock Received But Not Billed.
		inner join `tabAccount` acc on acc.name = gle.account and acc.root_type = 'Expense'
		where {conditions}
		group by gle.cost_code
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.cost_code: flt(r.amount) for r in rows}


def get_descriptions(codes):
	if not codes:
		return {}
	rows = frappe.get_all("Cost Code", filters={"name": ["in", codes]},
	                      fields=["name", "description"])
	return {r.name: r.description for r in rows}
