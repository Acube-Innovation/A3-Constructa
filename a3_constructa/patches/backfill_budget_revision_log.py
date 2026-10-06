# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01C: replay every BOQ approved before the Budget Revision Log existed, in
the order it happened, so the log starts complete: approvals as Original or BOQ
Revision rows, cancellations taking their lines back out. Amended BOQs without a
revision reason get a placeholder so the log row says something."""

import frappe

PLACEHOLDER = "Recorded before revision reasons were required."


def execute():
	logged = set(frappe.get_all("Budget Revision Log", filters={"reference_doctype": "BOQ"}, pluck="reference_name", distinct=True))
	for name in frappe.get_all("BOQ", filters={"docstatus": ["in", [1, 2]]}, order_by="creation", pluck="name"):
		if name in logged:
			continue
		boq = frappe.get_doc("BOQ", name)
		if boq.amended_from and not boq.revision_reason:
			boq.db_set("revision_reason", PLACEHOLDER, update_modified=False)
		approved_on = boq.boq_date
		boq.log_budget(posted_on=approved_on, posted_by=boq.modified_by)
		if boq.docstatus == 2:
			boq.log_budget(cancel=True, posted_on=boq.modified, posted_by=boq.modified_by)
