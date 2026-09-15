# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import add_days, cint, getdate


class ProcurementPlan(Document):
	def validate(self):
		self.set_recommended_pr_date()

	def set_recommended_pr_date(self):
		"""Build sheet head 21 row 20: recommended_pr_date = required date - lead time.

		The date a purchase requisition has to be raised for the material to
		arrive on site in time. Read-only on the form, so it is derived here.
		A row with no required date has nothing to work back from and is left
		empty rather than given a date measured from today.
		"""
		for row in self.items:
			if not row.required_on_site_date:
				row.recommended_pr_date = None
				continue

			row.recommended_pr_date = add_days(
				getdate(row.required_on_site_date), -cint(row.lead_time_days)
			)
