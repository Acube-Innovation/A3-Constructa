# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01B: WBS Allocation is now submittable. Submit every existing draft that
passes the 100% rule (and the other checks on submit); leave the rest as drafts
and print them, with the reason, so someone can put them right."""

import frappe


def execute():
	kept = []
	for name in frappe.get_all("WBS Allocation", filters={"docstatus": 0}, order_by="creation", pluck="name"):
		frappe.db.savepoint("wbs_allocation_patch")
		try:
			doc = frappe.get_doc("WBS Allocation", name)
			doc.flags.ignore_permissions = True
			doc.submit()
		except frappe.ValidationError as e:
			frappe.db.rollback(save_point="wbs_allocation_patch")
			frappe.local.message_log = []
			kept.append((name, frappe.utils.strip_html(str(e))))

	for name, reason in kept:
		print(f"WBS Allocation {name} left as draft: {reason}")
