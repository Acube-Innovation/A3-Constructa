# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Change Event - catalogue 3.4: a change noticed on an awarded job, before anyone
knows what it is worth or who pays for it.

It is logged against the award as soon as it is seen (Open), roughly priced
(Priced), and then decided: it becomes a Variation Order for the client, is
Absorbed within the contract, becomes a Claim, or is Closed. Until it is decided
its rough cost and days are open exposure on the award (Change Event Register).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

OPEN = ("Open", "Priced", "Claim")
DECIDED_NEEDS_NOTE = ("Absorbed", "Claim", "Closed")


class ChangeEvent(Document):
	def validate(self):
		self.validate_award()
		self.validate_wbs()
		self.validate_status()

	def validate_award(self):
		if frappe.db.get_value("Awarded Quotation", self.awarded_quotation, "status") == "Cancelled":
			frappe.throw(_("{0} is cancelled, so it cannot take a change event.").format(self.awarded_quotation))

	def validate_wbs(self):
		if self.wbs and self.project and frappe.db.get_value("WBS", self.wbs, "project") != self.project:
			frappe.throw(_("WBS {0} is not part of project {1}, the award's project.").format(self.wbs, self.project))

	def validate_status(self):
		if self.rough_days and self.rough_days < 0:
			frappe.throw(_("Rough days cannot be negative."))
		if self.status == "Priced" and not (flt(self.rough_cost) or self.rough_days):
			frappe.throw(_("Enter a rough cost or rough days before marking it Priced."), title=_("Not priced"))
		if self.status == "Became VO" and not self.variation_order:
			frappe.throw(_("Use Create Variation Order; the status changes to Became VO when the order is made."))
		if self.variation_order and self.status != "Became VO":
			frappe.throw(_("This change is already {0}; its status stays Became VO.").format(self.variation_order))
		if self.status in DECIDED_NEEDS_NOTE and not (self.decision_note or "").strip():
			frappe.throw(_("Say why it is {0} (Decision Note).").format(_(self.status)), title=_("Decision note needed"))


@frappe.whitelist()
def make_variation_order(change_event: str) -> str:
	"""Create Variation Order: a draft VO for the award with one line for the WBS at
	the rough cost and the rough days as time extension; the event becomes Became VO."""
	ce = frappe.get_doc("Change Event", change_event)
	ce.check_permission("write")
	frappe.has_permission("Variation Order", "create", throw=True)
	if ce.variation_order:
		frappe.throw(_("{0} already became {1}.").format(ce.name, ce.variation_order))
	if ce.status != "Priced":
		frappe.throw(_("Price the change first: a variation order is made from a Priced change event."), title=_("Not priced"))

	vo = frappe.new_doc("Variation Order")
	vo.update({
		"subject": ce.title,
		"awarded_quotation": ce.awarded_quotation,
		"customer": ce.customer,
		"project": ce.project,
		"currency": ce.currency,
		"vo_date": today(),
		"variation_type": "Omission" if flt(ce.rough_cost) < 0 else "Addition",
		"status": "Draft",
		"time_extension_days": ce.rough_days,
		"reason": _("From change event {0} ({1}): {2}").format(ce.name, _(ce.source), ce.description),
	})
	vo.append("items", {"description": ce.title[:140], "wbs": ce.wbs, "cost_head": ce.cost_head, "qty": 1,
	                    "uom": "Lump Sum", "rate": flt(ce.rough_cost)})
	vo.insert()
	ce.db_set({"variation_order": vo.name, "status": "Became VO"})
	ce.add_comment("Info", _("Became variation order {0}").format(vo.name))
	return vo.name
