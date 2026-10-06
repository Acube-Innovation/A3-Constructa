# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget vs WBS - build sheet head 20, row 13.

Budget comes from submitted WBS Allocations (the allocated amount per WBS
node), plus one "Unallocated" row per cost head for the approved BOQ budget not
yet allocated, so the budget column adds up to the approved BOQ. Actuals
come from GL Entry via the `wbs` custom field this app adds. GL Entry ships with
no WBS of its own, so a voucher only appears here once the workspace that
creates it stamps that field - until then the actual column reads zero and the
variance equals the budget.

Since P-03B the budget is shown three ways: the original (allocated BOQ budget),
the changes made outside the BOQ (approved variations and budget transfers, from
the Budget Revision Log), and the revised budget the two add up to. Variance and
% utilised are measured against the revised budget.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.api.budget_allocation import budget_changes, unallocated_by_cost_head, unallocated_row_label


def execute(filters=None):
	filters = frappe._dict(filters or {})
	budget = get_budget(filters)
	changes = budget_changes("wbs", filters.get("project"), filters.get("company"), filters.get("wbs"))
	actual = get_actual(filters)

	wbs_names = sorted((set(budget) | set(actual) | set(changes)) - {None})
	names = get_wbs_names(wbs_names)

	data = [row(wbs, names.get(wbs), budget.get(wbs), changes.get(wbs), actual.get(wbs)) for wbs in wbs_names]
	if changes.get(None) and not filters.get("wbs"):
		data.append(row(None, _("Variations and transfers not on a WBS"), 0, changes[None], 0))

	if not filters.get("wbs"):
		for entry in unallocated_by_cost_head(filters.get("project"), filters.get("company")):
			data.append({
				"wbs": None,
				"wbs_name": unallocated_row_label(entry),
				"original_budget": entry["amount"],
				"budget_changes": 0,
				"budget_amount": entry["amount"],
				"actual_amount": 0,
				"variance": entry["amount"],
				"percent_utilised": 0,
				"is_unallocated": 1,
			})

	return get_columns(), data


def row(wbs, name, original, change, spent):
	original, change, spent = flt(original), flt(change), flt(spent)
	revised = original + change
	return {
		"wbs": wbs,
		"wbs_name": name,
		"original_budget": original,
		"budget_changes": change,
		"budget_amount": revised,
		"actual_amount": spent,
		"variance": revised - spent,
		# A WBS with spend but no budget is the case worth seeing, so it is
		# shown as 100% rather than hidden behind a division by zero.
		"percent_utilised": (spent / revised * 100) if revised else (100 if spent else 0),
	}


def get_columns():
	return [
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link",
		 "options": "WBS", "width": 160},
		{"fieldname": "wbs_name", "label": _("WBS Name"), "fieldtype": "Data", "width": 320},
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
	conditions = ["alloc.docstatus = 1", "alloc.wbs is not null"]
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
		-- Cost only: since P-01D the WBS and cost code are on every GL row a line
		-- makes, including stock and Stock Received But Not Billed.
		inner join `tabAccount` acc on acc.name = gle.account and acc.root_type = 'Expense'
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
