# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.nestedset import NestedSet


class WBS(NestedSet):
	def validate(self):
		self.set_wbs_level()

	def set_wbs_level(self):
		"""Build sheet head 4, row 21: wbs_level is auto-set from tree depth.

		A root node is level 1 and each child is one deeper than its parent, so
		the field is read-only on the form and derived here instead. Reading the
		parent's stored level rather than walking to the root keeps this O(1);
		it holds because a parent is always saved before its children.
		"""
		parent = self.get("parent_wbs")
		if not parent:
			self.wbs_level = 1
			return

		self.wbs_level = (frappe.db.get_value("WBS", parent, "wbs_level") or 0) + 1
