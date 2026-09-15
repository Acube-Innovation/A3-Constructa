# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class BOQ(Document):
	def validate(self):
		self.calculate_amounts()

	def calculate_amounts(self):
		"""Build sheet head 17 row 5 and head 18: amount and budget_amount are derived.

		`amount` is the BOQ line value (qty x rate); `budget_amount` is the same
		arithmetic on the approved figures, which is what the Budget doctype and
		the Budget vs WBS report read. Both are read-only on the form, so they are
		computed here rather than trusted from the client.
		"""
		total = 0.0
		for row in self.items:
			row.amount = flt(row.boq_qty) * flt(row.rate)
			row.budget_amount = flt(row.approved_qty) * flt(row.approved_rate)
			total += flt(row.amount)

		self.total_amount = total

	def on_submit(self):
		# The workflow drives `status`; this only covers a submit made without one.
		if self.status not in ("Approved", "Rejected"):
			self.db_set("status", "Approved")

	def on_cancel(self):
		self.db_set("status", "Rejected")
