# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class WorkCertificate(Document):
	def validate(self):
		self.calculate_amounts()
		self.validate_quantities()

	def calculate_amounts(self):
		"""Certify this period's work and split it into retention and net payable.

		Retention is withheld from the subcontractor now and released at
		defect-liability expiry, so `net_payable` - not `amount` - is what the
		Finance workspace pays against.
		"""
		total = retention = net = 0.0

		for row in self.items:
			row.amount = flt(row.this_period_qty) * flt(row.rate)
			row.retention_amount = flt(row.amount) * flt(row.retention_percent) / 100.0
			row.net_payable = flt(row.amount) - flt(row.retention_amount)

			total += flt(row.amount)
			retention += flt(row.retention_amount)
			net += flt(row.net_payable)

		self.total_amount = total
		self.total_retention = retention
		self.total_net_payable = net

	def validate_quantities(self):
		"""Certifying more than was contracted is the error worth catching here.

		`previous_qty` is what earlier certificates already certified, so the
		running total is what must stay within the contracted quantity.
		"""
		for row in self.items:
			if not flt(row.contracted_qty):
				continue

			certified = flt(row.previous_qty) + flt(row.this_period_qty)
			if certified > flt(row.contracted_qty):
				frappe.throw(
					_("Row {0}: certified quantity {1} exceeds the contracted quantity {2} for {3}.").format(
						row.idx, certified, flt(row.contracted_qty), row.item_code
					)
				)
