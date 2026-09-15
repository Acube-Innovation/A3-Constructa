# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget vs WBS - build sheet head 20, row 13.

Budget comes from WBS Allocation (the allocated amount per WBS node); actuals
come from GL Entry via the `wbs` custom field this app adds. GL Entry ships with
no WBS of its own, so a voucher only appears here once the workspace that
creates it stamps that field - until then the actual column reads zero and the
variance equals the budget.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	budget = get_budget(filters)
	actual = get_actual(filters)

	wbs_names = sorted(set(budget) | set(actual))
	names = get_wbs_names(wbs_names)

	data = []
	for wbs in wbs_names:
		budgeted = flt(budget.get(wbs))
		spent = flt(actual.get(wbs))
		data.append({
			"wbs": wbs,
			"wbs_name": names.get(wbs),
			"budget_amount": budgeted,
			"actual_amount": spent,
			"variance": budgeted - spent,
			# A WBS with spend but no budget is the case worth seeing, so it is
			# shown as 100% rather than hidden behind a division by zero.
			"percent_utilised": (spent / budgeted * 100) if budgeted else (100 if spent else 0),
		})

	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link",
		 "options": "WBS", "width": 160},
		{"fieldname": "wbs_name", "label": _("WBS Name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "budget_amount", "label": _("Budget Amount"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "actual_amount", "label": _("Actual Amount"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "percent_utilised", "label": _("% Utilised"),
		 "fieldtype": "Percent", "width": 110},
	]


def get_budget(filters):
	conditions = ["alloc.docstatus < 2", "alloc.wbs is not null"]
	values = {}
	if filters.get("project"):
		conditions.append("alloc.project = %(project)s")
		values["project"] = filters.project
	if filters.get("wbs"):
		conditions.append("alloc.wbs = %(wbs)s")
		values["wbs"] = filters.wbs

	rows = frappe.db.sql(
		"""
		select alloc.wbs as wbs, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		where {conditions}
		group by alloc.wbs
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.wbs: flt(r.amount) for r in rows}


def get_actual(filters):
	conditions = ["gle.is_cancelled = 0", "gle.wbs is not null", "gle.wbs != ''"]
	values = {}
	if filters.get("project"):
		conditions.append("gle.project = %(project)s")
		values["project"] = filters.project
	if filters.get("wbs"):
		conditions.append("gle.wbs = %(wbs)s")
		values["wbs"] = filters.wbs
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
		select gle.wbs as wbs, sum(gle.debit) - sum(gle.credit) as amount
		from `tabGL Entry` gle
		where {conditions}
		group by gle.wbs
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.wbs: flt(r.amount) for r in rows}


def get_wbs_names(wbs_names):
	if not wbs_names:
		return {}
	rows = frappe.get_all("WBS", filters={"name": ["in", wbs_names]},
	                      fields=["name", "wbs_name"])
	return {r.name: r.wbs_name for r in rows}
