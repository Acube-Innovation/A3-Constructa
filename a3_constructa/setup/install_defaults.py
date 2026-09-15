# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Baseline records this app owns.

`run()` is called from `after_install` and again from `after_migrate`, so it
must be safe to call any number of times: every helper checks for the record
before creating it, and none of them overwrite a record a user has since edited.

Phase 1 deliberately seeds nothing yet — the construction domain model arrives
in Phase 2. The structure is here so that the first record added is added in the
right place, rather than through the UI and into this site's database only.

When a record created here is also one ERPNext or a user can edit, prefer
creating it here over a fixture: code can be conditional and can migrate an
existing row, whereas a fixture overwrites on every migrate.
"""

import frappe

# Records keyed by the doctype they belong to. Phase 2 fills these in; the
# creation helpers below already handle them.
ITEM_GROUPS: list[dict] = []
ASSET_CATEGORIES: list[dict] = []
STOCK_ENTRY_TYPES: list[dict] = []


def _ensure(doctype: str, name: str, values: dict):
	"""Create `name` if it is absent. Never modifies an existing record."""
	if frappe.db.exists(doctype, name):
		return
	doc = frappe.new_doc(doctype)
	doc.update(values)
	doc.flags.ignore_mandatory = True
	doc.flags.ignore_permissions = True
	doc.insert()


def create_item_groups():
	for group in ITEM_GROUPS:
		_ensure("Item Group", group["item_group_name"], group)


def create_asset_categories():
	for category in ASSET_CATEGORIES:
		_ensure("Asset Category", category["asset_category_name"], category)


def create_stock_entry_types():
	for entry_type in STOCK_ENTRY_TYPES:
		_ensure("Stock Entry Type", entry_type["name"], entry_type)


def run():
	"""Seed every baseline record. Idempotent."""
	create_item_groups()
	create_asset_categories()
	create_stock_entry_types()
