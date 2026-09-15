# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Landed Cost Analysis - build sheet head 41, row 25.

What an imported item actually cost by the time it reached the warehouse: the
FOB rate off the purchase receipt, plus the freight, duty, clearing and inland
charges apportioned to it by Landed Cost Vouchers, ending at the valuation rate
stock is carried at.

ERPNext already apportions those charges - `landed_cost_voucher_amount` on the
receipt line is the total of them - so this report splits that total back out by
charge type rather than recomputing the apportionment. The split is pro rata on
each line's share of the voucher's applicable amount, which is the same basis
ERPNext used to apply it.

Cost code comes from the `cost_code` custom field this app adds to Purchase
Receipt Item, fetched from the purchase order line.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_receipt_items(filters)
	charges = get_charge_split(rows)

	data = []
	for r in rows:
		split = charges.get(r.name, {})
		fob = flt(r.base_net_amount)
		freight = flt(split.get("freight"))
		duty = flt(split.get("duty"))
		clearing = flt(split.get("clearing"))
		inland = flt(split.get("inland"))
		other = flt(r.landed_cost_voucher_amount) - (freight + duty + clearing + inland)

		data.append({
			"purchase_receipt": r.parent,
			"item_code": r.item_code,
			"cost_code": r.cost_code,
			"qty": flt(r.qty),
			"fob_rate": flt(r.base_net_rate),
			"fob_amount": fob,
			"freight": freight,
			"duty": duty,
			"clearing": clearing,
			"inland": inland,
			"other_charges": other,
			"valuation_rate": flt(r.valuation_rate),
			"landed_amount": fob + flt(r.landed_cost_voucher_amount),
		})

	if filters.get("group_by_cost_code"):
		data = group_by_cost_code(data)
		return cost_code_columns(), data

	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "purchase_receipt", "label": _("Purchase Receipt"), "fieldtype": "Link",
		 "options": "Purchase Receipt", "width": 150},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link",
		 "options": "Item", "width": 160},
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 130},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "fob_rate", "label": _("FOB Rate"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "fob_amount", "label": _("FOB Amount"), "fieldtype": "Currency",
		 "width": 130},
		{"fieldname": "freight", "label": _("Freight"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "duty", "label": _("Duty"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "clearing", "label": _("Clearing"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "inland", "label": _("Inland"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "other_charges", "label": _("Other"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "landed_amount", "label": _("Landed Amount"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "valuation_rate", "label": _("Valuation Rate"), "fieldtype": "Currency",
		 "width": 140},
	]


def cost_code_columns():
	return [
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 160},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "fob_amount", "label": _("FOB Amount"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "freight", "label": _("Freight"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "duty", "label": _("Duty"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "clearing", "label": _("Clearing"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "inland", "label": _("Inland"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "other_charges", "label": _("Other"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "landed_amount", "label": _("Landed Amount"), "fieldtype": "Currency",
		 "width": 150},
	]


def get_receipt_items(filters):
	conditions = ["pr.docstatus = 1"]
	values = {}
	if filters.get("company"):
		conditions.append("pr.company = %(company)s")
		values["company"] = filters.company
	if filters.get("purchase_receipt"):
		conditions.append("pr.name = %(purchase_receipt)s")
		values["purchase_receipt"] = filters.purchase_receipt
	if filters.get("cost_code"):
		conditions.append("pri.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code
	if filters.get("from_date"):
		conditions.append("pr.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("pr.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		"""
		select pri.name, pri.parent, pri.item_code, pri.cost_code, pri.qty,
		       pri.base_net_rate, pri.base_net_amount, pri.valuation_rate,
		       pri.landed_cost_voucher_amount
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent
		where {conditions}
		order by pr.posting_date desc, pri.idx
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


# Landed Cost Voucher charge descriptions are free text, so charges are bucketed
# by keyword. Anything unmatched lands in "Other" rather than being dropped.
BUCKETS = (
	("freight", ("freight", "ocean", "sea", "air")),
	("duty", ("duty", "customs", "tariff")),
	("clearing", ("clearing", "cnf", "chb", "handling", "port")),
	("inland", ("inland", "transport", "trucking", "haulage", "lorry")),
)


def bucket_for(description: str) -> str:
	text = (description or "").lower()
	for bucket, keywords in BUCKETS:
		if any(k in text for k in keywords):
			return bucket
	return "other"


def get_charge_split(rows):
	"""Split each line's applied landed cost back out by charge type."""
	if not rows:
		return {}

	receipts = {r.parent for r in rows}
	vouchers = frappe.get_all(
		"Landed Cost Purchase Receipt",
		filters={"receipt_document": ["in", list(receipts)], "docstatus": 1},
		pluck="parent",
	)
	if not vouchers:
		return {}

	split = {}
	for voucher_name in set(vouchers):
		voucher = frappe.get_doc("Landed Cost Voucher", voucher_name)

		totals = {}
		for tax in voucher.taxes:
			totals[bucket_for(tax.description)] = \
				totals.get(bucket_for(tax.description), 0) + flt(tax.base_amount)

		# ERPNext apportions on the applicable charges basis; the item rows carry
		# the resulting share, so pro rata on applicable_charges reproduces it.
		grand = sum(flt(i.applicable_charges) for i in voucher.items)
		if not grand:
			continue

		for item in voucher.items:
			share = flt(item.applicable_charges) / grand
			target = split.setdefault(item.purchase_receipt_item, {})
			for bucket, amount in totals.items():
				target[bucket] = target.get(bucket, 0) + amount * share

	return split


def group_by_cost_code(rows):
	buckets = {}
	for r in rows:
		key = r["cost_code"] or _("Not Set")
		b = buckets.setdefault(key, {"cost_code": key, "qty": 0, "fob_amount": 0,
		                             "freight": 0, "duty": 0, "clearing": 0,
		                             "inland": 0, "other_charges": 0, "landed_amount": 0})
		for f in ("qty", "fob_amount", "freight", "duty", "clearing", "inland",
		          "other_charges", "landed_amount"):
			b[f] += r[f]
	return sorted(buckets.values(), key=lambda r: r["landed_amount"], reverse=True)
