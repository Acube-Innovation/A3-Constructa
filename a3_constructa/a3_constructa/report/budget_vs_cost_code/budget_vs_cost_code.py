# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget vs Cost Code - build sheet head 20, row 14.

The same comparison as Budget vs WBS, grouped one level down: cost_code sits on
the WBS Allocation Item row rather than on the parent, so the budget side groups
by the child field. Actuals come from GL Entry via the `cost_code` custom field
this app adds, and read zero until the spending workspaces stamp it.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	budget = get_budget(filters)
	actual = get_actual(filters)

	codes = sorted(set(budget) | set(actual))
	descriptions = get_descriptions(codes)

	data = []
	for code in codes:
		budgeted = flt(budget.get(code))
		spent = flt(actual.get(code))
		data.append({
			"cost_code": code,
			"description": descriptions.get(code),
			"budget_amount": budgeted,
			"actual_amount": spent,
			"variance": budgeted - spent,
			"percent_utilised": (spent / budgeted * 100) if budgeted else (100 if spent else 0),
		})

	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 160},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 240},
		{"fieldname": "budget_amount", "label": _("Budget Amount"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "actual_amount", "label": _("Actual Amount"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "percent_utilised", "label": _("% Utilised"),
		 "fieldtype": "Percent", "width": 110},
	]


def get_budget(filters):
	conditions = ["alloc.docstatus < 2", "item.cost_code is not null", "item.cost_code != ''"]
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
