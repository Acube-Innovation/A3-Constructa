"""P-03B: approved variations now move the WBS budget. Write the Budget Revision
Log rows for variation orders approved before that, and stamp their approver."""

import frappe


def execute():
	if not frappe.db.table_exists("Budget Revision Log"):
		return
	from a3_constructa.a3_constructa.doctype.variation_order.variation_order import sync_budget

	for name in frappe.get_all("Variation Order", filters={"status": "Approved"}, pluck="name"):
		vo = frappe.get_doc("Variation Order", name)
		if not vo.project:
			vo.db_set("project", frappe.db.get_value("Awarded Quotation", vo.awarded_quotation, "project"), update_modified=False)
		sync_budget(vo)
		if not vo.approved_by:
			vo.db_set("approved_by", vo.modified_by or vo.owner, update_modified=False)
