# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""BOQ vs Consumption - build sheet head 49, row 23.

What the BOQ allowed against what has actually been issued, per cost code. The
over-consumption flag is the point of the report: material issued beyond the
BOQ quantity is either a variation to be claimed or a loss to be explained, and
either way somebody needs to see it while the job is still running.

Approved quantities are used where the BOQ has them, since that is what was
signed off; the original quantity is the fallback for a BOQ still in draft.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	boq = get_boq_quantities(filters)
	issued = get_issued_quantities(filters)

	data = []
	for cost_code in sorted(set(boq) | set(issued)):
		b = boq.get(cost_code, {})
		boq_qty = flt(b.get("qty"))
		issued_qty = flt(issued.get(cost_code))
		data.append({
			"cost_code": cost_code,
			"item_code": b.get("item_code"),
			"uom": b.get("uom"),
			"boq_qty": boq_qty,
			"issued_qty": issued_qty,
			"balance_qty": boq_qty - issued_qty,
			"consumed_percent": (issued_qty / boq_qty * 100) if boq_qty else
			(100 if issued_qty else 0),
			# Issued with no BOQ line at all is over-consumption too - it was
			# never budgeted.
			"over_consumed": 1 if issued_qty > boq_qty else 0,
		})

	if filters.get("only_over_consumed"):
		data = [r for r in data if r["over_consumed"]]

	data.sort(key=lambda r: (-r["over_consumed"], -r["consumed_percent"]))
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 160},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link",
		 "options": "Item", "width": 160},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM",
		 "width": 80},
		{"fieldname": "boq_qty", "label": _("BOQ Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "issued_qty", "label": _("Issued Qty"), "fieldtype": "Float",
		 "width": 110},
		{"fieldname": "balance_qty", "label": _("Balance Qty"), "fieldtype": "Float",
		 "width": 110},
		{"fieldname": "consumed_percent", "label": _("% Consumed"), "fieldtype": "Percent",
		 "width": 120},
		{"fieldname": "over_consumed", "label": _("Over Consumed"), "fieldtype": "Check",
		 "width": 130},
	]


def get_boq_quantities(filters):
	conditions = ["boq.docstatus < 2", "item.cost_code is not null", "item.cost_code != ''"]
	values = {}
	if filters.get("project"):
		conditions.append("boq.project = %(project)s")
		values["project"] = filters.project
	if filters.get("cost_code"):
		conditions.append("item.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code

	rows = frappe.db.sql(
		"""
		select item.cost_code,
		       sum(case when item.approved_qty > 0 then item.approved_qty
		                else item.boq_qty end) as qty,
		       max(item.item_code) as item_code,
		       max(item.uom) as uom
		from `tabBOQ Item` item
		inner join `tabBOQ` boq on boq.name = item.parent
		where {conditions}
		group by item.cost_code
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.cost_code: {"qty": r.qty, "item_code": r.item_code, "uom": r.uom} for r in rows}


def get_issued_quantities(filters):
	conditions = [
		"sle.is_cancelled = 0",
		"sle.voucher_type = 'Stock Entry'",
		"sle.actual_qty < 0",
		"se.purpose = 'Material Issue'",
		"sed.cost_code is not null",
		"sed.cost_code != ''",
	]
	values = {}
	if filters.get("project"):
		conditions.append("sed.project = %(project)s")
		values["project"] = filters.project
	if filters.get("cost_code"):
		conditions.append("sed.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code
	if filters.get("to_date"):
		conditions.append("sle.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select sed.cost_code, sum(abs(sle.actual_qty)) as qty
		from `tabStock Ledger Entry` sle
		inner join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		inner join `tabStock Entry` se on se.name = sle.voucher_no
		where {conditions}
		group by sed.cost_code
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {r.cost_code: flt(r.qty) for r in rows}
