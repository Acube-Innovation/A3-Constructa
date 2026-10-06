# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-04: Client IPC records the day it went to the client. Certificates sent
before the field existed take the day they were created, the closest date on record."""

import frappe


def execute():
	for ipc in frappe.get_all("Client IPC", filters={"status": ["!=", "Draft"], "submitted_on": ["is", "not set"]},
	                          fields=["name", "creation"]):
		frappe.db.set_value("Client IPC", ipc.name, "submitted_on", ipc.creation.date(), update_modified=False)
