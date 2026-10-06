# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Custom HTML Blocks this app ships, kept as real files.

A Custom HTML Block is a record whose HTML, CSS and JavaScript are text fields.
Exported as a fixture, that code would sit as escaped strings inside JSON where
no one can read a diff. Instead each block is a folder under
`a3_constructa/a3_constructa/custom_html_block/<folder>/` holding `<folder>.css`
and `<folder>.js` (and `<folder>.html` if it needs its own markup), and `sync()`
writes them into the record on install and on every `bench migrate`.

The workspace overviews share their tabs, helpers and styles, so `_shared/`
holds `overview.html`, `overview.css` and `overview.js`: each block's CSS and JS
are appended to the shared ones, and a block without its own HTML uses the
shared markup.

The files are the source of truth. Unlike the records in install_defaults.py,
these are code, not data, so `sync()` overwrites edits made from the desk.
Change the files instead.
"""

import os

import frappe

# Record name -> folder under a3_constructa/a3_constructa/custom_html_block/
CUSTOM_HTML_BLOCKS = {
	"WBS & Cost Structure Overview": "wbs_cost_structure_overview",
	"CRM & Estimating Overview": "crm_estimating_overview",
	"Contracts & Awards Overview": "contracts_awards_overview",
	"Sales & Billing Overview": "sales_billing_overview",
	"Master Data Overview": "master_data_overview",
	"Planning & Budgeting Overview": "planning_overview",
	"Procurement Overview": "procurement_overview",
	"Delivery & Logistics Overview": "delivery_logistics_overview",
	"Inventory Movement Overview": "inventory_movement_overview",
	"Asset & Equipment Overview": "asset_equipment_overview",
	"HR & Time Overview": "hr_time_overview",
	"Finance & Accounting Overview": "finance_accounting_overview",
	# Drawn by the Award Procurement page, not by a workspace.
	"Award Procurement View": "award_procurement_view",
}

SHARED_FOLDER = "_shared"
SHARED_NAME = "overview"


def sync():
	"""Create or update every block from its files. Idempotent."""
	for name, folder in CUSTOM_HTML_BLOCKS.items():
		code = _read_block(folder)

		if frappe.db.exists("Custom HTML Block", name):
			doc = frappe.get_doc("Custom HTML Block", name)
			if not doc.private and all(doc.get(field) == value for field, value in code.items()):
				continue
			doc.update(code)
			doc.private = 0
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.new_doc("Custom HTML Block")
			doc.update(code)
			doc.private = 0
			doc.insert(ignore_permissions=True, set_name=name)


def _read_block(folder: str) -> dict:
	shared = _source(SHARED_FOLDER, SHARED_NAME)
	own = _source(folder, folder)
	return {
		"html": own("html") or shared("html"),
		"style": shared("css") + "\n" + own("css"),
		"script": shared("js") + "\n" + own("js"),
	}


def _source(folder: str, name: str):
	"""Return a reader for `<folder>/<name>.<extension>`, giving "" for a file that is not there."""
	path = frappe.get_app_path("a3_constructa", "a3_constructa", "custom_html_block", folder)

	def read(extension: str) -> str:
		file = os.path.join(path, f"{name}.{extension}")
		if not os.path.exists(file):
			return ""
		with open(file, encoding="utf-8") as f:
			return f.read()

	return read
