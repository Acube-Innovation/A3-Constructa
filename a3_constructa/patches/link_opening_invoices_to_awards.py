# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-04: the invoice an opening IPC records belongs to that IPC's award; link the
ones submitted before Client IPC did it on submit."""

import frappe


def execute():
	for ipc in frappe.get_all("Client IPC", filters={"docstatus": 1, "opening_invoice": ["is", "set"]}, fields=["awarded_quotation", "opening_invoice"]):
		if not frappe.db.get_value("Sales Invoice", ipc.opening_invoice, "awarded_quotation"):
			frappe.db.set_value("Sales Invoice", ipc.opening_invoice, "awarded_quotation", ipc.awarded_quotation, update_modified=False)
