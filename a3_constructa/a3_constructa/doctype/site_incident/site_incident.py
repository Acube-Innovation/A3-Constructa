# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Site Incident - catalogue 6.9: a near miss, an injury, damage or a spill.

Reported as Open, investigated (Under investigation), then Closed once the root
cause is written and every action is done. A lost-time incident or an
environmental one is High severity at least, and a lost-time one names the
person and the days lost; the HSE Register counts the days since the last one.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, today

from a3_constructa.hse import default_site, not_in_future

SERIOUS = ("Lost time", "Environmental")
LEVELS = ("Low", "Medium", "High", "Critical")


class SiteIncident(Document):
	def validate(self):
		default_site(self)
		not_in_future(self.occurred_on, _("Occurred On"))
		if self.is_new():
			self.reported_by = self.reported_by or frappe.session.user
		for p in self.persons_involved:
			if p.person_type == "Employee" and p.employee and not p.person_name:
				p.person_name = frappe.db.get_value("Employee", p.employee, "employee_name")
			if not (p.person_name or p.employee):
				frappe.throw(_("Row {0}: name the person involved.").format(p.idx), title=_("Persons involved"))
		self.days_lost = sum(cint(p.days_lost) for p in self.persons_involved)
		if self.incident_type in SERIOUS and LEVELS.index(self.severity) < LEVELS.index("High"):
			frappe.throw(_("Lost-time and environmental incidents are High severity at least."), title=_("Severity"))
		if self.incident_type == "Lost time" and not (self.persons_involved and self.days_lost):
			frappe.throw(_("A lost-time incident names the person injured and the days lost."), title=_("Lost time"))
		if self.status == "Under investigation" and not (self.investigation or "").strip():
			frappe.throw(_("Write what the investigation has found so far."), title=_("Investigation"))
		if self.status == "Closed":
			if not (self.root_cause or "").strip():
				frappe.throw(_("Write the root cause before closing."), title=_("Close"))
			open_actions = [a.action for a in self.actions if not a.done]
			if open_actions:
				frappe.throw(_("Actions still open: {0}.").format("; ".join(open_actions)), title=_("Close"))
			if self.incident_type in SERIOUS and not self.actions:
				frappe.throw(_("A lost-time or environmental incident closes with at least one action taken."), title=_("Close"))
			self.closed_on = self.closed_on or today()
		else:
			self.closed_on = None
