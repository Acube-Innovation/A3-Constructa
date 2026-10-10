# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Toolbox Talk - catalogue 6.9: a short safety briefing on site, who gave it and
who was there. A subcontractor's crew is counted by headcount; an employee once."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from a3_constructa.hse import default_site, not_in_future


class ToolboxTalk(Document):
	def validate(self):
		default_site(self)
		not_in_future(self.talk_date, _("The talk date"))
		seen = set()
		for row in self.attendees:
			if row.attendee_type == "Employee":
				if not row.employee:
					frappe.throw(_("Row {0}: choose the employee.").format(row.idx), title=_("Attendees"))
				if row.employee in seen:
					frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.employee_name or row.employee), title=_("Attendees"))
				seen.add(row.employee)
				row.supplier, row.headcount = None, 1
			else:
				if not row.supplier:
					frappe.throw(_("Row {0}: choose the subcontractor.").format(row.idx), title=_("Attendees"))
				if cint(row.headcount) < 1:
					frappe.throw(_("Row {0}: how many of {1}'s workers were there?").format(row.idx, row.supplier), title=_("Attendees"))
				row.employee = row.employee_name = None
		self.total_attendance = sum(cint(r.headcount) for r in self.attendees)
