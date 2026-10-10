# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Alert Rule - catalogue 13.6. What it looks for and who it tells: see api/alerts.py."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_constructa.api.alerts import UNITS


class AlertRule(Document):
	def validate(self):
		self.threshold_unit = UNITS.get(self.condition, "days")
		if flt(self.threshold) < 0:
			frappe.throw(_("The threshold cannot be negative."))
		if not self.recipients:
			frappe.throw(_("Add at least one recipient: a user or a role."))
		for r in self.recipients:
			if r.recipient_type == "User" and not r.user or r.recipient_type == "Role" and not r.role:
				frappe.throw(_("Recipient row {0}: pick the {1}.").format(r.idx, _(r.recipient_type).lower()))
