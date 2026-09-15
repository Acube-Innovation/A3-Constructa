# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Cost Code Wise Costing - build sheet head 71, row 32 (and row 37 by WBS).

The cost control report: what was budgeted, what is committed on orders, what
has actually been spent, and how much room is left. Everything else in this
head hangs off it, and the "Budget Utilisation %" number card reads its
`percent_consumed` column.

Committed and actual are kept apart on purpose. A cost code can be inside budget
on actuals and already over-committed on purchase orders, and only seeing both
tells you that before the invoices arrive.

Do not rename the `percent_consumed`, `budget`, `committed` or `actual`
fieldnames: the Legend warns that report-backed number cards fail silently when
a column they name disappears, and row 59's card names this one.
"""

import frappe
from frappe import _
from frappe.utils import flt

GROUP_FIELDS = {
	"Cost Code": "cost_code",
	"WBS": "wbs",
	"Cost Head": "cost_head",
	"Project": "project",
}
LINK_OPTIONS = {"cost_code": "Cost Code", "wbs": "WBS",
                "cost_head": "Cost Head", "project": "Project"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by = filters.get("group_by") or "Cost Code"
	field = GROUP_FIELDS.get(group_by, "cost_code")

	budget = get_budget(filters, field)
	committed = get_committed(filters, field)
	actual = get_actual(filters, field)

	data = []
	for key in sorted(set(budget) | set(committed) | set(actual)):
		b = flt(budget.get(key))
		c = flt(committed.get(key))
		a = flt(actual.get(key))
		consumed = a + c
		data.append({
			"grouping": key,
			"budget": b,
			"committed": c,
			"actual": a,
			"balance": b - consumed,
			# Committed money is spent for control purposes even though no
			# invoice has landed, so utilisation counts both.
			"percent_consumed": (consumed / b * 100) if b else (100 if consumed else 0),
		})

	if filters.get("only_over_budget"):
		data = [r for r in data if r["balance"] < 0]

	data.sort(key=lambda r: r["percent_consumed"], reverse=True)
	return get_columns(group_by, field), data


def get_columns(label, field):
	return [
		{"fieldname": "grouping", "label": _(label), "fieldtype": "Link",
		 "options": LINK_OPTIONS.get(field), "width": 180},
		{"fieldname": "budget", "label": _("Budget"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "committed", "label": _("Committed"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "actual", "label": _("Actual"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "percent_consumed", "label": _("% Consumed"), "fieldtype": "Percent",
		 "width": 130},
	]


def get_budget(filters, field):
	"""Allocated amounts, the same source Budget vs WBS uses so the two agree."""
	source = {"cost_code": "item.cost_code", "wbs": "alloc.wbs",
	          "cost_head": "alloc.cost_head", "project": "alloc.project"}[field]
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
		values, as_dict=True,
	)
	return {r.grouping: flt(r.amount) for r in rows}


def get_committed(filters, field):
	"""Submitted purchase orders, less what has already been invoiced."""
	source = {"cost_code": "poi.cost_code", "wbs": "poi.wbs",
	          "cost_head": "poi.cost_head", "project": "po.project"}[field]
	conditions = ["po.docstatus = 1", "%s is not null" % source, "%s != ''" % source]
	values = {}
	if filters.get("project"):
		conditions.append("po.project = %(project)s")
		values["project"] = filters.project
	if filters.get("company"):
		conditions.append("po.company = %(company)s")
		values["company"] = filters.company

	rows = frappe.db.sql(
		"""
		select {source} as grouping,
		       sum(poi.base_amount - (poi.billed_amt * ifnull(po.conversion_rate, 1))) as amount
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where {conditions}
		group by {source}
		""".format(source=source, conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	# A fully billed order commits nothing further; its cost is in `actual`.
	return {r.grouping: max(flt(r.amount), 0) for r in rows}


def get_actual(filters, field):
	"""Actual spend, from the GL and from material issued out of store.

	Two sources because they do not overlap: the GL carries invoiced cost
	through the wbs and cost_code fields this app adds, while material consumed
	from stock is a stock ledger movement whose attribution lives on the issue
	line.
	"""
	totals = {}

	if field in ("wbs", "cost_code", "project"):
		gl_field = {"wbs": "gle.wbs", "cost_code": "gle.cost_code",
		            "project": "gle.project"}[field]
		conditions = ["gle.is_cancelled = 0", "%s is not null" % gl_field,
		              "%s != ''" % gl_field]
		values = {}
		if filters.get("company"):
			conditions.append("gle.company = %(company)s")
			values["company"] = filters.company
		if filters.get("project"):
			conditions.append("gle.project = %(project)s")
			values["project"] = filters.project
		if filters.get("from_date"):
			conditions.append("gle.posting_date >= %(from_date)s")
			values["from_date"] = filters.from_date
		if filters.get("to_date"):
			conditions.append("gle.posting_date <= %(to_date)s")
			values["to_date"] = filters.to_date

		for r in frappe.db.sql(
			"""
			select {gl_field} as grouping, sum(gle.debit) - sum(gle.credit) as amount
			from `tabGL Entry` gle
			where {conditions}
			group by {gl_field}
			""".format(gl_field=gl_field, conditions=" and ".join(conditions)),
			values, as_dict=True,
		):
			totals[r.grouping] = totals.get(r.grouping, 0) + flt(r.amount)

	# Material issued to the job.
	sed_field = {"cost_code": "sed.cost_code", "wbs": "sed.wbs",
	             "cost_head": "sed.cost_head", "project": "sed.project"}[field]
	conditions = ["sle.is_cancelled = 0", "sle.voucher_type = 'Stock Entry'",
	              "sle.actual_qty < 0", "se.purpose = 'Material Issue'",
	              "%s is not null" % sed_field, "%s != ''" % sed_field]
	values = {}
	if filters.get("project"):
		conditions.append("sed.project = %(project)s")
		values["project"] = filters.project
	if filters.get("from_date"):
		conditions.append("sle.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("sle.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	for r in frappe.db.sql(
		"""
		select {sed_field} as grouping, sum(abs(sle.stock_value_difference)) as amount
		from `tabStock Ledger Entry` sle
		inner join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		inner join `tabStock Entry` se on se.name = sle.voucher_no
		where {conditions}
		group by {sed_field}
		""".format(sed_field=sed_field, conditions=" and ".join(conditions)),
		values, as_dict=True,
	):
		totals[r.grouping] = totals.get(r.grouping, 0) + flt(r.amount)

	return totals
