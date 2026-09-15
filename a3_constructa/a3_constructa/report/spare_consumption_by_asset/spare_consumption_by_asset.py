# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Spare Consumption by Asset - build sheet head 57, row 38.

Which parts each machine eats, how often and for how much. A part consumed
repeatedly by one asset is usually a symptom rather than a coincidence, so the
frequency column sits next to the value.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)

	if filters.get("view") == "By Asset":
		return asset_columns(), summarise_by_asset(rows)

	return get_columns(), detail(rows)


def get_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset",
		 "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_code", "label": _("Part"), "fieldtype": "Link", "options": "Item",
		 "width": 160},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "frequency", "label": _("Times Consumed"), "fieldtype": "Int",
		 "width": 140},
	]


def asset_columns():
	return [
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset",
		 "width": 140},
		{"fieldname": "asset_name", "label": _("Asset Name"), "fieldtype": "Data", "width": 190},
		{"fieldname": "asset_category", "label": _("Category"), "fieldtype": "Link",
		 "options": "Asset Category", "width": 160},
		{"fieldname": "distinct_parts", "label": _("Distinct Parts"), "fieldtype": "Int",
		 "width": 130},
		{"fieldname": "qty", "label": _("Total Qty"), "fieldtype": "Float", "width": 110},
		{"fieldname": "value", "label": _("Total Value"), "fieldtype": "Currency", "width": 150},
	]


def get_rows(filters):
	conditions = ["ar.docstatus < 2"]
	values = {}
	if filters.get("asset"):
		conditions.append("ar.asset = %(asset)s")
		values["asset"] = filters.asset
	if filters.get("asset_category"):
		conditions.append("a.asset_category = %(asset_category)s")
		values["asset_category"] = filters.asset_category
	if filters.get("item_code"):
		conditions.append("c.item_code = %(item_code)s")
		values["item_code"] = filters.item_code
	if filters.get("from_date"):
		conditions.append("ar.failure_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("ar.failure_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		"""
		select ar.asset, a.asset_name, a.asset_category,
		       c.item_code, c.consumed_quantity as qty, c.total_value as value
		from `tabAsset Repair Consumed Item` c
		inner join `tabAsset Repair` ar on ar.name = c.parent
		left join `tabAsset` a on a.name = ar.asset
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def detail(rows):
	buckets = {}
	for r in rows:
		key = (r.asset, r.item_code)
		b = buckets.setdefault(key, {"asset": r.asset, "asset_name": r.asset_name,
		                             "item_code": r.item_code, "qty": 0.0,
		                             "value": 0.0, "frequency": 0})
		b["qty"] += flt(r.qty)
		b["value"] += flt(r.value)
		b["frequency"] += 1
	return sorted(buckets.values(), key=lambda r: r["value"], reverse=True)


def summarise_by_asset(rows):
	buckets = {}
	for r in rows:
		b = buckets.setdefault(r.asset, {"asset": r.asset, "asset_name": r.asset_name,
		                                 "asset_category": r.asset_category,
		                                 "qty": 0.0, "value": 0.0, "_parts": set()})
		b["qty"] += flt(r.qty)
		b["value"] += flt(r.value)
		b["_parts"].add(r.item_code)

	data = []
	for b in buckets.values():
		b["distinct_parts"] = len(b.pop("_parts"))
		data.append(b)
	# Top-consuming assets first, which is what the row asks to surface.
	return sorted(data, key=lambda r: r["value"], reverse=True)
