# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Hooks on the standard Asset.

Build sheet head 51, row 2: "Configure the naming series on Asset Category
(e.g. HEQ-.####)".

ERPNext names every asset from a single `Asset.naming_series`, so heavy
equipment, vehicles and IT kit all share one run of numbers. A plant register is
easier to work with when the number says what the thing is, which is what the
row is after. Asset Category gains an `asset_naming_series` field and the asset
takes it from its category.
"""

import frappe


def set_naming_series_from_category(doc, method=None):
	"""Name the asset from its category's series, if that category sets one.

	Hooked on `before_naming`, which frappe runs from `set_new_name` before the
	series is consumed - anything later leaves the asset already named.

	A category with no series set falls through to the standard Asset series, so
	this is opt-in per category and changes nothing until someone fills it in.
	"""
	if not doc.is_new() or not doc.get("asset_category"):
		return

	series = frappe.db.get_value("Asset Category", doc.asset_category, "asset_naming_series")
	if series:
		doc.naming_series = series
