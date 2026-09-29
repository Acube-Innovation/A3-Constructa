# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""A change the client asks for after the award: more work, less work, or different work.

Only an Approved variation counts. Once approved, its value and time extension
roll up onto the Awarded Quotation as the revised contract value and revised
completion date, which is what the award and the Planning & Budgeting overview
report.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from a3_constructa.a3_constructa.doctype.awarded_quotation.awarded_quotation import refresh_variation_totals


class VariationOrder(Document):
	def validate(self):
		self.validate_award()
		self.calculate_total()
		self.validate_sign()
		if self.status == "Approved" and not self.approved_date:
			self.approved_date = today()

	def validate_award(self):
		if frappe.db.get_value("Awarded Quotation", self.awarded_quotation, "status") == "Cancelled":
			frappe.throw(_("{0} is cancelled, so it cannot take a variation.").format(self.awarded_quotation))

	def calculate_total(self):
		total = 0.0
		for row in self.items:
			row.amount = flt(row.qty) * flt(row.rate)
			total += row.amount
		self.total_amount = total

	def validate_sign(self):
		"""An omission takes work out, so it has to reduce the contract value."""
		if self.variation_type == "Omission" and flt(self.total_amount) > 0:
			frappe.throw(_("An omission reduces the contract. Enter the omitted quantities as negative numbers."))

	def on_update(self):
		refresh_variation_totals(self.awarded_quotation)
		previous = self.get_doc_before_save()
		if previous and previous.awarded_quotation != self.awarded_quotation:
			refresh_variation_totals(previous.awarded_quotation)

	def on_trash(self):
		refresh_variation_totals(self.awarded_quotation, exclude=self.name)
