# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-04D: retention release invoices are now flagged, so the final account can tell
them from invoices for work. Flag the releases P-04C made, which the awards link."""

import frappe


def execute():
	for half in (1, 2):
		for name in frappe.get_all("Awarded Quotation", filters={f"retention_release_{half}": ["is", "set"]}, pluck=f"retention_release_{half}"):
			frappe.db.set_value("Sales Invoice", name, "is_retention_release", 1, update_modified=False)
