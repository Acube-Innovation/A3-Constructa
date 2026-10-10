# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Install-time hooks.

`before_install` runs *before* the DocType sync, which is the only safe place to
create the Roles that our DocType permission rows link to — a missing Role makes
`sync_for()` fail with a link validation error on a fresh site.

Every role name is prefixed, so another app on the same bench can never end up
sharing one Role record with this one. ERPNext already ships a "Projects
Manager" and a "Stock User"; "Constructa Project Manager" is unambiguous.

Everything here is idempotent by construction: each step checks for what it is
about to create. That is what lets `after_migrate` re-run it on every
`bench migrate` and lets a fresh site reproduce the whole app from source.
"""

import frappe

# `desk_access` decides where a role's holders work. Site-level roles keep the
# desk for now; a portal for site staff is a later phase.
A3_CONSTRUCTA_ROLES = [
	{"role_name": "A3 Constructa Admin", "desk_access": 1},
	{"role_name": "Constructa Project Manager", "desk_access": 1},
	{"role_name": "Constructa Site Engineer", "desk_access": 1},
	{"role_name": "Constructa Quantity Surveyor", "desk_access": 1},
	{"role_name": "Constructa Store Keeper", "desk_access": 1},
	{"role_name": "Constructa Contractor", "desk_access": 0},
]


def create_roles():
	"""Idempotently create the A3 Constructa roles."""
	for role in A3_CONSTRUCTA_ROLES:
		if frappe.db.exists("Role", role["role_name"]):
			continue
		doc = frappe.new_doc("Role")
		doc.update(role)
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)


def ensure_item_group_root():
	"""The tree root our Item Group fixtures hang off.

	ERPNext creates "All Item Groups" in its setup wizard, but a new site - and
	every new Frappe Cloud site - installs its apps before the wizard runs, so
	the fixture sync would find no parent and fail the install. The wizard skips
	records that already exist, so creating the root here is safe.
	"""
	if frappe.db.exists("Item Group", "All Item Groups"):
		return
	frappe.get_doc({"doctype": "Item Group", "item_group_name": "All Item Groups", "is_group": 1}).insert(
		ignore_permissions=True
	)


def before_install():
	create_roles()
	ensure_item_group_root()
	frappe.db.commit()


def before_migrate():
	"""A site migrated before its setup wizard has run hits the same missing root."""
	if "erpnext" in frappe.get_installed_apps():
		ensure_item_group_root()


def after_install():
	from a3_constructa.setup import accounting_dimensions, custom_html_blocks
	from a3_constructa.setup.install_defaults import run as install_defaults

	create_roles()
	install_defaults()
	accounting_dimensions.sync()
	custom_html_blocks.sync()
	frappe.db.commit()


def after_migrate():
	"""Keep roles, defaults, accounting dimensions and Custom HTML Blocks in sync on every `bench migrate`."""
	from a3_constructa.setup import accounting_dimensions, custom_html_blocks
	from a3_constructa.setup.install_defaults import run as install_defaults

	create_roles()
	install_defaults()
	accounting_dimensions.sync()
	custom_html_blocks.sync()


def before_tests():
	"""Prepare the site for `bench run-tests --app a3_constructa`."""
	from a3_constructa.setup.install_defaults import run as install_defaults

	frappe.flags.skip_test_records = True

	create_roles()
	install_defaults()
	frappe.db.commit()
