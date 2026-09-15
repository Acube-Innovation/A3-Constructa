# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Hooks on the standard Stock Entry.

Two things the build sheet asks for that ERPNext does not do on its own:

  head 48 row 19 - "set expense_account and cost_center from the Cost Code
  master so the issue posts to the correct project GL head";

  heads 43 and 46 - a MIN-.YYYY.- series for a material issue note and a
  MRN-.YYYY.- series for a material receipt note.
"""

import frappe

# heads 43 and 46: the entry type that should carry each series.
SERIES_BY_ENTRY_TYPE = {
	"Material Issue Note (MIN)": "MIN-.YYYY.-",
	"Material Receipt Note (MRN)": "MRN-.YYYY.-",
}


def set_naming_series(doc, method=None):
	"""Pick the series that matches the entry type.

	Hooked on `before_naming`, which frappe runs from `set_new_name` before the
	series is consumed - setting this any later leaves the document already
	named MAT-STE-.

	Only applies to a new document, and only when the series still holds the
	ERPNext default: a series deliberately chosen on the form is left alone, and
	an existing document is never renamed.
	"""
	if not doc.is_new():
		return

	series = SERIES_BY_ENTRY_TYPE.get(doc.get("stock_entry_type"))
	if not series:
		return

	if doc.get("naming_series") in (None, "", "MAT-STE-.YYYY.-"):
		doc.naming_series = series


def set_cost_code_accounting(doc, method=None):
	"""Copy the Cost Code's account and cost centre onto each issue line.

	Without this a material issue debits whatever default the item or company
	carries - Stock Adjustment, typically - and every project's consumption
	lands in the same account. The Cost Code master is where a project's GL head
	and cost centre are recorded, so a line tagged with one follows it.

	This deliberately overwrites what is already on the line. ERPNext fills
	expense_account with its own default during its `validate`, which runs
	before this hook, so honouring only empty fields would mean the Cost Code
	never won. Choosing a cost code is the explicit instruction; if a line needs
	a different account, clear the cost code on that line.
	"""
	for row in doc.items:
		if not row.get("cost_code"):
			continue

		cost_code = frappe.db.get_value(
			"Cost Code", row.cost_code, ["account", "cost_center"], as_dict=True
		)
		if not cost_code:
			continue

		if cost_code.account:
			row.expense_account = cost_code.account

		if cost_code.cost_center:
			row.cost_center = cost_code.cost_center
