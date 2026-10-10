"""P-02E: quotations made before the Quotation Margin Approval workflow get the
state matching where they are, and revision 0 where they are a first issue."""

import frappe

STATES = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


def execute():
	if frappe.db.get_value("Singles", {"doctype": "A3 Constructa Settings", "field": "min_margin_percent"}, "value", order_by=None) is None:
		frappe.db.set_single_value("A3 Constructa Settings", "min_margin_percent", 10)
	if not frappe.db.has_column("Quotation", "workflow_state"):
		return
	for docstatus, state in STATES.items():
		frappe.db.sql(
			"update `tabQuotation` set workflow_state = %s where docstatus = %s and ifnull(workflow_state, '') = ''",
			(state, docstatus),
		)
	frappe.db.sql("update `tabQuotation` set revision_no = 0 where revision_no is null and ifnull(amended_from, '') = ''")
