# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CostCode(Document):
	def validate(self):
		# Cost Code is an Accounting Dimension (P-01D). ERPNext's dimension pickers
		# skip records with disabled set, so an Inactive cost code drops out of
		# every invoice, journal and claim line without overriding their query.
		self.disabled = 1 if self.status == "Inactive" else 0
