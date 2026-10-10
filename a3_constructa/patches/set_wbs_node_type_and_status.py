# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01A: give existing WBS nodes a node type from their tree position, and make
every node that already carries postings Active, so the new posting check does
not lock documents that were valid before it existed."""

import frappe

from a3_constructa.a3_constructa.doctype.wbs.wbs import node_type_from_position

POSTING_TABLES = [
	"Material Request Item",
	"Purchase Order Item",
	"Purchase Receipt Item",
	"Stock Entry Detail",
	"Timesheet Detail",
	"Expense Claim Detail",
	"GL Entry",
	"WBS Allocation",
	"Variation Order Item",
	"BOQ Item",
]


def execute():
	posted = set()
	for doctype in POSTING_TABLES:
		if frappe.db.has_column(doctype, "wbs"):
			posted.update(frappe.get_all(doctype, filters={"wbs": ["is", "set"]}, pluck="wbs", distinct=True))

	for node in frappe.get_all("WBS", fields=["name", "is_group", "parent_wbs", "cost_head", "node_type", "status"]):
		values = {}
		if not node.node_type:
			values["node_type"] = node_type_from_position(node.is_group, node.parent_wbs, node.cost_head)
		if node.name in posted and node.status != "Active":
			values["status"] = "Active"
		elif not node.status:
			values["status"] = "Draft"
		if values:
			frappe.db.set_value("WBS", node.name, values, update_modified=False)
