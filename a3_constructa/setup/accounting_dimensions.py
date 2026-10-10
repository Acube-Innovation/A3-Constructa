# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 1.3, 1.7, 9.9: WBS and Cost Code as ERPNext Accounting Dimensions.

As dimensions, ERPNext itself carries them from every buying, selling, stock and
journal line onto the GL Entry it posts, and General Ledger, Trial Balance and
the P&L can filter by them. ERPNext adds the field to each accounting doctype
only where a field of that name is missing, so the `wbs` and `cost_code`
custom fields this app already puts on GL Entry, Material Request Item,
Purchase Order Item and the rest are reused, never doubled.

Run on install and on every migrate; it only creates what is missing.
"""

import json

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import make_dimension_in_accounting_doctypes

DIMENSIONS = (("WBS", "WBS"), ("Cost Code", "Cost Code"))  # (document type, label)

# Only an Active cost code can be picked, wherever a cost_code field appears.
ACTIVE_COST_CODE = json.dumps([["Cost Code", "status", "=", "Active"]])


def sync():
	for document_type, label in DIMENSIONS:
		name = frappe.db.get_value("Accounting Dimension", {"document_type": document_type})
		if name:
			doc = frappe.get_doc("Accounting Dimension", name)
		else:
			doc = frappe.new_doc("Accounting Dimension")
			doc.document_type = document_type
			doc.label = label
			doc.flags.ignore_permissions = True
			# Inserting enqueues the field creation; it is done in-line below instead,
			# so the fields exist as soon as migrate finishes.
			frappe.flags.in_test, was = True, frappe.flags.in_test
			try:
				doc.insert()
			finally:
				frappe.flags.in_test = was
		# Creates the field on any accounting doctype added since (by ERPNext,
		# HRMS or this app) and skips the ones that already have it.
		make_dimension_in_accounting_doctypes(doc)
	restrict_to_active_cost_codes()
	# Keep the hidden `disabled` flag in step with Status for cost codes saved
	# before it existed; ERPNext's dimension pickers read it.
	frappe.db.sql("update `tabCost Code` set disabled = if(status = 'Inactive', 1, 0) where disabled != if(status = 'Inactive', 1, 0)")
	frappe.flags.accounting_dimensions = None


def restrict_to_active_cost_codes():
	"""Filter every cost_code link to Active cost codes. The fields this app ships
	carry the filter in their own JSON or fixture; this covers the ones ERPNext
	created for the dimension."""
	for field in frappe.get_all(
		"Custom Field",
		filters={"fieldname": "cost_code", "fieldtype": "Link", "options": "Cost Code"},
		fields=["name", "dt", "link_filters"],
	):
		if field.link_filters != ACTIVE_COST_CODE:
			frappe.db.set_value("Custom Field", field.name, "link_filters", ACTIVE_COST_CODE, update_modified=False)
			frappe.clear_cache(doctype=field.dt)
