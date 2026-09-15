# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Project-wise Material Consumption - build sheet head 49, row 22.

Quantity and value consumed, grouped by project, cost head, WBS or cost code.

Value comes from Stock Ledger Entry rather than the Stock Entry line, so the
figure ties to the stock ledger and the GL. Stock Ledger Entry carries only
`project`, so the other three dimensions are read from the Stock Entry Detail
row the ledger entry points at through `voucher_detail_no` - which avoids
duplicating those fields onto every ledger entry.
"""

import frappe
from frappe import _
from frappe.utils import flt

GROUP_FIELDS = {
	"Project": "project",
	"Cost Head": "cost_head",
	"WBS": "wbs",
	"Cost Code": "cost_code",
}

LINK_OPTIONS = {
	"project": "Project", "cost_head": "Cost Head", "wbs": "WBS", "cost_code": "Cost Code",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by = filters.get("group_by") or "Project"
	field = GROUP_FIELDS.get(group_by, "project")

	rows = get_rows(filters)

	buckets = {}
	for r in rows:
		key = r.get(field) or _("Not Set")
		b = buckets.setdefault(key, {"grouping": key, "qty": 0.0, "value": 0.0, "entries": 0})
		# actual_qty is negative for an issue; consumption is reported positive.
		b["qty"] += abs(flt(r.actual_qty))
		b["value"] += abs(flt(r.stock_value_difference))
		b["entries"] += 1

	data = sorted(buckets.values(), key=lambda r: r["value"], reverse=True)
	return get_columns(group_by, field), data


def get_columns(label, field):
	return [
		{"fieldname": "grouping", "label": _(label), "fieldtype": "Link",
		 "options": LINK_OPTIONS.get(field), "width": 200},
		{"fieldname": "qty", "label": _("Qty Consumed"), "fieldtype": "Float", "width": 140},
		{"fieldname": "value", "label": _("Value Consumed"), "fieldtype": "Currency",
		 "width": 160},
		{"fieldname": "entries", "label": _("Ledger Entries"), "fieldtype": "Int",
		 "width": 130},
	]


def get_rows(filters):
	# actual_qty < 0 is stock leaving; combined with a Material Issue voucher
	# that is consumption rather than a transfer between warehouses.
	conditions = [
		"sle.is_cancelled = 0",
		"sle.voucher_type = 'Stock Entry'",
		"sle.actual_qty < 0",
		"se.purpose = 'Material Issue'",
	]
	values = {}

	if filters.get("company"):
		conditions.append("sle.company = %(company)s")
		values["company"] = filters.company
	if filters.get("project"):
		conditions.append("sed.project = %(project)s")
		values["project"] = filters.project
	if filters.get("from_date"):
		conditions.append("sle.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("sle.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		"""
		select sle.actual_qty, sle.stock_value_difference,
		       sed.project, sed.cost_head, sed.wbs, sed.cost_code
		from `tabStock Ledger Entry` sle
		inner join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		inner join `tabStock Entry` se on se.name = sle.voucher_no
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
