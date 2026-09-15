# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Shared helpers and the names the demo is built around.

Every demo record is either named with the MBK prefix or linked to the demo
project, which is what lets `teardown` find them again without touching
anything a real user created.
"""

import frappe
from frappe.utils import add_days, nowdate

# ------------------------------------------------------------------ the story
PROJECT_NAME = "Mbandaka University Campus"

# Head 3 of the build sheet lists these five packages by name, and the Cost Head
# reports filter on exactly these strings - including the lower-case "works".
COST_HEADS = ["University", "Hospital", "Road works", "External works", "Temporary works"]

PREFIX = "MBK"

# The demo runs over the last eight weeks so that ageing, attendance and the
# cash-flow forecast all have something either side of today.
def day(offset: int) -> str:
	return add_days(nowdate(), offset)


def company() -> str:
	return frappe.defaults.get_defaults().get("company") or frappe.get_all(
		"Company", pluck="name"
	)[0]


def abbr(company_name: str | None = None) -> str:
	return frappe.get_cached_value("Company", company_name or company(), "abbr")


def ensure(doctype: str, name: str, values: dict, submit: bool = False):
	"""Get the record if it exists, otherwise create it. Never edits an existing one."""
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)

	doc = frappe.new_doc(doctype)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	if submit:
		doc.submit()
	return doc


def ensure_by(doctype: str, filters: dict, values: dict, submit: bool = False):
	"""Same, for doctypes that name themselves - match on a field instead."""
	existing = frappe.db.get_value(doctype, filters, "name")
	if existing:
		return frappe.get_doc(doctype, existing)

	doc = frappe.new_doc(doctype)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	if submit:
		doc.submit()
	return doc


def project() -> str:
	"""The demo project's name, which ERPNext assigns rather than us."""
	return frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")


def warehouse(short_name: str) -> str:
	return "%s - %s" % (short_name, abbr())


def account(account_type: str, hint: str | None = None, root_type: str | None = None):
	filters = {"company": company(), "is_group": 0}
	if account_type:
		filters["account_type"] = account_type
	if root_type:
		filters["root_type"] = root_type
	names = frappe.get_all("Account", filters=filters, pluck="name", order_by="name")
	if hint:
		for n in names:
			if hint.lower() in n.lower():
				return n
	return names[0] if names else None


def log(message: str):
	print("  %s" % message)
