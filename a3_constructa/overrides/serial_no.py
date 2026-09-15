# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Hooks on the standard Serial No.

Build sheet head 55, row 23 wants the small-tools register filtered by item
group: "Tool ID / Barcode" lists Serial Nos where item_group is Small Tools.

Serial No has an `item_group` field but ERPNext never fills it - serials are
created from stock movements, which carry the item code and nothing else. The
field therefore sits empty on every serial in the system and the register is
permanently blank. This copies it from the item as each serial is created.
"""

import frappe


def set_item_group(doc, method=None):
	"""Stamp the serial with its item's group, so it can be filtered by it."""
	if doc.get("item_group") or not doc.get("item_code"):
		return

	doc.item_group = frappe.db.get_value("Item", doc.item_code, "item_group")


def backfill_item_groups():
	"""Fill in serials that were created before this hook existed.

	Safe to run repeatedly: only touches serials whose group is still empty.
	"""
	rows = frappe.get_all(
		"Serial No",
		filters={"item_group": ["in", ["", None]]},
		fields=["name", "item_code"],
	)
	for row in rows:
		group = frappe.db.get_value("Item", row.item_code, "item_group")
		if group:
			frappe.db.set_value("Serial No", row.name, "item_group", group,
			                    update_modified=False)
	frappe.db.commit()
	return len(rows)
