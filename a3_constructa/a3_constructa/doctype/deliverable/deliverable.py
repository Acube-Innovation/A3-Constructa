# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Something we owe the client under an award: a drawing, a submittal, a handover pack.

The status carries the review cycle: Submitted, then Approved, or Revise and
Resubmit and round again. Each resubmission is a new revision.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, today

# Statuses that mean the client has had it at least once.
SUBMITTED_STATUSES = ("Submitted", "Approved", "Revise and Resubmit", "Rejected")


class Deliverable(Document):
	def validate(self):
		self.count_resubmission()
		self.stamp_dates()
		self.validate_dates()

	def count_resubmission(self):
		"""Sending it back in after Revise and Resubmit is the next revision, submitted today."""
		previous = self.get_doc_before_save()
		if previous and previous.status == "Revise and Resubmit" and self.status == "Submitted":
			self.revision = cint(self.revision) + 1
			self.submitted_date = today()

	def stamp_dates(self):
		"""Fill in the date of the step the status has reached, if it was left empty."""
		if self.status in SUBMITTED_STATUSES and not self.submitted_date:
			self.submitted_date = today()
		if self.status == "Approved" and not self.approved_date:
			self.approved_date = today()

	def validate_dates(self):
		if self.submitted_date and self.approved_date and date_diff(self.approved_date, self.submitted_date) < 0:
			frappe.throw(_("It cannot be approved before it was submitted."))
