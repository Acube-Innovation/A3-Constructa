# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Material Request lines fetched from a BOQ (Get Items From > BOQ).

A line keeps the BOQ line it buys in `boq_item`, which is what the procurement
reports trace through to the order and the receipt. Saving checks that link
still holds together and warns, without stopping anyone, when the requests for
a BOQ line add up to more than it approved: a site may need a margin for
wastage, but whoever raises the request should see it.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.api.boq_procurement import _conversion_factor


def validate_boq_lines(doc, method=None):
	rows = [row for row in doc.items if row.get("boq_item")]
	if not rows:
		return

	sources = {
		line.name: line
		for line in frappe.get_all(
			"BOQ Item",
			filters={"name": ["in", list({row.boq_item for row in rows})], "parenttype": "BOQ"},
			fields=["name", "parent", "item_code", "uom", "boq_qty", "approved_qty"],
		)
	}
	approved_boqs = set(
		frappe.get_all("BOQ", filters={"name": ["in", list({s.parent for s in sources.values()})], "docstatus": 1}, pluck="name")
	)

	for row in rows:
		source = sources.get(row.boq_item)
		if not source or (row.boq and row.boq != source.parent):
			frappe.throw(_("Row {0}: the BOQ line it was fetched from no longer exists in {1}.").format(row.idx, row.boq))
		if source.item_code != row.item_code:
			frappe.throw(
				_("Row {0}: the BOQ line is for {1}, not {2}. Fetch the line again from the BOQ.").format(
					row.idx, frappe.bold(source.item_code), frappe.bold(row.item_code)
				)
			)
		if source.parent not in approved_boqs:
			frappe.throw(_("Row {0}: BOQ {1} is not approved.").format(row.idx, source.parent))
		row.boq = source.parent

	_warn_if_over_boq(doc, rows, sources)


def _warn_if_over_boq(doc, rows, sources):
	asked_here = {}
	for row in rows:
		asked_here[row.boq_item] = asked_here.get(row.boq_item, 0) + flt(row.stock_qty or flt(row.qty) * flt(row.conversion_factor or 1))

	asked_elsewhere = {}
	for other in frappe.get_all(
		"Material Request Item",
		filters={"boq_item": ["in", list(asked_here)], "docstatus": ["<", 2], "parent": ["!=", doc.name or ""]},
		fields=["boq_item", "stock_qty"],
	):
		asked_elsewhere[other.boq_item] = asked_elsewhere.get(other.boq_item, 0) + flt(other.stock_qty)

	over = []
	for boq_item, here in asked_here.items():
		source = sources[boq_item]
		stock_uom = frappe.get_cached_value("Item", source.item_code, "stock_uom")
		allowed = (flt(source.approved_qty) or flt(source.boq_qty)) * _conversion_factor(source.item_code, source.uom, stock_uom)
		total = here + asked_elsewhere.get(boq_item, 0)
		if total > allowed + 1e-6:
			over.append(
				_("{0} in {1}: {2} {3} requested against {4} approved").format(
					frappe.bold(source.item_code), source.parent, flt(total, 3), stock_uom, flt(allowed, 3)
				)
			)

	if over:
		frappe.msgprint(
			"<br>".join(over),
			title=_("More than the BOQ approved"),
			indicator="orange",
		)
