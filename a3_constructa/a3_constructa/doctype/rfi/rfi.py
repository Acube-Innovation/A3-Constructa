# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""RFI - catalogue 6.10: a request for information from site to the designers.

An RFI is Open until the answer is entered (Answered, on the day it came) and
Closed once site has acted on it. When the answer costs money or time, it is
marked as a cost or time impact and "Raise change event" logs the change on the
project's award (P-03A), linked both ways; such an RFI closes only once its
change event exists. Overdue RFIs lists the open ones past their required date.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class RFI(Document):
	def validate(self):
		if self.is_new():
			self.raised_by = self.raised_by or frappe.session.user
		if getdate(self.raised_on) > getdate(today()):
			frappe.throw(_("Raised On can't be in the future."), title=_("Date"))
		if getdate(self.required_by) < getdate(self.raised_on):
			frappe.throw(_("The answer can't be required before the RFI is raised."), title=_("Date"))
		if self.wbs and frappe.db.get_value("WBS", self.wbs, "project") != self.project:
			frappe.throw(_("WBS {0} is not part of project {1}.").format(self.wbs, self.project), title=_("WBS"))
		if self.drawing and frappe.db.get_value("Drawing Register", self.drawing, "project") != self.project:
			frappe.throw(_("Drawing {0} belongs to another project.").format(self.drawing), title=_("Drawing"))
		answered = bool((self.answer or "").strip())
		if not answered:
			if self.status != "Open" or self.answered_on or self.cost_impact or self.time_impact:
				frappe.throw(_("Enter the answer first."), title=_("No answer yet"))
			return
		self.answered_on = self.answered_on or today()
		if getdate(self.answered_on) < getdate(self.raised_on) or getdate(self.answered_on) > getdate(today()):
			frappe.throw(_("Answered On must fall between the day it was raised and today."), title=_("Date"))
		if self.status == "Open":
			self.status = "Answered"
		if self.status == "Closed" and (self.cost_impact or self.time_impact) and not self.change_event:
			frappe.throw(_("The answer costs money or time: raise its change event before closing."), title=_("Change event"))


@frappe.whitelist()
def raise_change_event(rfi: str) -> str:
	"""A Change Event on the project's award for an answer with a cost or time impact."""
	doc = frappe.get_doc("RFI", rfi)
	doc.check_permission("write")
	if doc.change_event:
		return doc.change_event
	if not (doc.cost_impact or doc.time_impact):
		frappe.throw(_("Tick Cost Impact or Time Impact first."), title=_("No impact"))
	award = frappe.db.get_value("Awarded Quotation", {"project": doc.project, "status": ["not in", ["Cancelled", "Completed"]]}, "name",
	                            order_by="award_date desc")
	if not award:
		frappe.throw(_("Project {0} has no live award to log the change against.").format(doc.project), title=_("No award"))
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	impacts = " and ".join(x for x, on in ((_("cost"), doc.cost_impact), (_("time"), doc.time_impact)) if on)
	ce = frappe.get_doc({
		"doctype": "Change Event", "title": f"{doc.name}: {doc.subject}"[:140], "awarded_quotation": award, "project": doc.project,
		"raised_on": today(), "raised_by": employee, "source": "RFI answer", "wbs": doc.wbs,
		"description": _("{0} ({1} impact).\nQuestion: {2}\nAnswer: {3}").format(doc.name, impacts, doc.question, doc.answer),
	})
	ce.insert()
	doc.db_set("change_event", ce.name)
	return ce.name
