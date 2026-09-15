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


def run():
	"""Seed every baseline record. Idempotent."""
	create_asset_categories()
