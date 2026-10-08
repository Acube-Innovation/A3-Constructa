# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Tender Clarification - catalogue 2.3: a question put to the client during a
tender (a "TQ"), and the client's answer.

Queries are numbered per tender (1, 2, 3, as the client's clarification log
numbers them). A query is Open until the client's answer is entered, then
Answered on the day it came back. An answer that changes what the work costs is
marked as a price impact, with a note of what changes, so the estimate is
revisited before the tender goes in. The Tender Register lists the open ones
against each tender's documents.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class TenderClarification(Document):
	def validate(self):
		if self.is_new():
			from a3_constructa.overrides.opportunity import refuse_if_no_go

			refuse_if_no_go(self.opportunity)
			self.raised_by = self.raised_by or frappe.session.user
		if not self.query_no:
			self.query_no = next_query_no(self.opportunity)
		if self.raised_on and getdate(self.raised_on) > getdate(today()):
			frappe.throw(_("Raised On can't be in the future."), title=_("Date"))
		self.set_status()

	def set_status(self):
		if (self.answer or "").strip():
			self.status = "Answered"
			self.answered_on = self.answered_on or today()
			if getdate(self.answered_on) < getdate(self.raised_on):
				frappe.throw(_("Answered On is before the query was raised."), title=_("Date"))
			if getdate(self.answered_on) > getdate(today()):
				frappe.throw(_("Answered On can't be in the future."), title=_("Date"))
		else:
			if self.answered_on or self.price_impact:
				frappe.throw(_("Enter the client's answer before its date or price impact."), title=_("No answer yet"))
			self.status = "Open"
		if self.price_impact and not (self.impact_note or "").strip():
			frappe.throw(_("Say what the answer changes in the Impact Note."), title=_("Price impact"))


def next_query_no(opportunity):
	last = frappe.db.sql("select max(query_no) from `tabTender Clarification` where opportunity = %s", opportunity)[0][0]
	return (last or 0) + 1
