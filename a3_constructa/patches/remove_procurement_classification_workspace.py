# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Procurement Classification was merged into the Procurement workspace.

	Its links now sit on Procurement's "Procurement Classification" card. `bench
	migrate` never deletes a record whose JSON has gone, so this removes it.
	"""
	if frappe.db.exists("Workspace", "Procurement Classification"):
		frappe.delete_doc("Workspace", "Procurement Classification", ignore_permissions=True, force=True)
