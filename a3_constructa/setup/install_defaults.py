# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Baseline records this app owns.

`run()` is called from `after_install` and again from `after_migrate`, so it
must be safe to call any number of times: every helper checks for the record
before creating it, and none of them overwrite a record a user has since edited.

Why Asset Categories live here and Item Groups do not
-----------------------------------------------------
Item Groups are plain master data with no dependency on the site, so they ship
as fixtures (see the `fixtures` list in hooks.py) and reinstall themselves on
`bench migrate`.

Asset Category cannot. Its `accounts` child table is mandatory and every row
needs a company and that company's fixed-asset account, so a fixture would hard
-code this site's "A3 Constructa Demo" and "Plants and Machineries - A3C" and
fail on any other site. The categories are therefore built here, resolving each
company's accounts by `account_type` at install time.
"""

import frappe

# Build sheet head 35 (rows 6-12). Useful lives and depreciation method are
# INFERRED - the sheet says only "(depreciation method, useful life)".
#
# `account_hint` picks the closest fixed-asset account by name; if no account
# matches, the first Fixed Asset account for the company is used instead, so
# this still works against a chart of accounts we have not seen.
#
# Vehicles has no finance book on purpose: row 11 is the one row of the seven
# that does not say "with its Asset Finance Book".
ASSET_CATEGORIES = [
	{"name": "Heavy Equipment", "account_hint": "Plant", "useful_life_years": 10},
	{"name": "Small Machinery", "account_hint": "Plant", "useful_life_years": 5},
	{"name": "Survey & Test Equipment", "account_hint": "Electronic", "useful_life_years": 5},
	{"name": "IT Equipment", "account_hint": "Electronic", "useful_life_years": 3},
	{"name": "Vehicles", "account_hint": "Capital", "useful_life_years": None},
	{"name": "Furniture & Office Equipment", "account_hint": "Furnitur", "useful_life_years": 5},
]


def _account(company: str, account_type: str, hint: str | None = None) -> str | None:
	"""A non-group account of `account_type` for `company`, preferring `hint`."""
	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "account_type": account_type, "is_group": 0},
		pluck="name",
		order_by="name",
	)
	if not accounts:
		return None
	if hint:
		for name in accounts:
			if hint.lower() in name.lower():
				return name
	return accounts[0]


def create_asset_categories():
	"""Idempotently create the asset categories, one accounts row per company."""
	companies = frappe.get_all("Company", pluck="name")
	if not companies:
		# A site with no Company yet - `after_install` on a bare site. The
		# categories cannot be built without accounts; after_migrate will pick
		# them up once the setup wizard has run.
		return

	for spec in ASSET_CATEGORIES:
		if frappe.db.exists("Asset Category", spec["name"]):
			continue

		accounts = []
		for company in companies:
			fixed_asset = _account(company, "Fixed Asset", spec["account_hint"])
			if not fixed_asset:
				# Nothing to depreciate against; skip this company rather than
				# insert a row Frappe will reject.
				continue
			accounts.append({
				"company_name": company,
				"fixed_asset_account": fixed_asset,
				"accumulated_depreciation_account": _account(company, "Accumulated Depreciation"),
				"depreciation_expense_account": _account(company, "Depreciation"),
			})

		if not accounts:
			continue

		doc = frappe.new_doc("Asset Category")
		doc.asset_category_name = spec["name"]
		for row in accounts:
			doc.append("accounts", row)

		if spec["useful_life_years"]:
			doc.append("finance_books", {
				"depreciation_method": "Straight Line",
				"total_number_of_depreciations": spec["useful_life_years"],
				"frequency_of_depreciation": 12,
			})

		doc.flags.ignore_permissions = True
		doc.insert()


# Build sheet head 66 row 11 and head 76 row 58, and the Legend: subcontractor
# retention is withheld from the certified amount and released at defect-
# liability expiry, so it is money owed but not yet payable. ERPNext has no
# native handling, so it needs an account of its own.
RETENTION_ACCOUNT_NAME = "Retention Payable"


def create_retention_account():
	"""Idempotently create a Retention Payable account per company.

	Placed under the company's payables group so retention shows in current
	liabilities alongside what is owed to the same subcontractors. Created here
	rather than as a fixture because account names carry the company abbreviation
	and the parent differs with each chart of accounts.
	"""
	for company in frappe.get_all("Company", fields=["name", "abbr"]):
		account_name = "%s - %s" % (RETENTION_ACCOUNT_NAME, company.abbr)
		if frappe.db.exists("Account", account_name):
			continue

		parent = _payables_parent(company.name)
		if not parent:
			# No payables group to hang it off; leave it to the implementation
			# rather than guess at the chart of accounts.
			continue

		doc = frappe.new_doc("Account")
		doc.account_name = RETENTION_ACCOUNT_NAME
		doc.parent_account = parent
		doc.company = company.name
		doc.account_type = "Payable"
		doc.root_type = "Liability"
		doc.is_group = 0
		doc.flags.ignore_permissions = True
		doc.insert()


def _payables_parent(company: str) -> str | None:
	"""The group account a payable belongs under, however the CoA is named.

	Tried in order of how specific the answer is. The standard chart of accounts
	leaves `account_type` blank on its "Accounts Payable" group, so matching on
	type alone finds nothing and falls all the way back to the liability root -
	which is how retention ended up outside current liabilities the first time.
	"""
	groups = frappe.get_all(
		"Account",
		filters={"company": company, "is_group": 1, "root_type": "Liability"},
		fields=["name", "account_type"],
		order_by="lft",
	)
	if not groups:
		return None

	by_type = [g.name for g in groups if g.account_type == "Payable"]
	if by_type:
		return by_type[0]

	for fragment in ("Accounts Payable", "Current Liabilities"):
		match = [g.name for g in groups if fragment.lower() in g.name.lower()]
		if match:
			return match[0]

	return groups[0].name


# Head 72 row 39 links ERPNext's Project Profitability report, and head 75 row
# 51 charts it. That report refuses to run until Standard Working Hours is set,
# so the app supplies a sensible default rather than shipping a link that errors.
DEFAULT_STANDARD_WORKING_HOURS = 8


def set_standard_working_hours():
	"""Fill in Standard Working Hours only when nobody has set it."""
	if frappe.db.get_value("HR Settings", None, "standard_working_hours"):
		return
	if not frappe.db.exists("DocType", "HR Settings"):
		return
	frappe.db.set_single_value(
		"HR Settings", "standard_working_hours", DEFAULT_STANDARD_WORKING_HOURS
	)


def run():
	"""Seed every baseline record. Idempotent."""
	create_asset_categories()
	create_retention_account()
	set_standard_working_hours()
