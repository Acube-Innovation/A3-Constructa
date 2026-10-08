# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Permit to Work - catalogue 6.9: written permission for high-risk work.

A permit is issued (Open) for one type of work, on a project and optionally a WBS,
to the person in charge, for at most 24 hours, with every precaution in place:
the standard list for its type fills in and the issuer adds to it. Only the
issuer, or a project manager, signs it off as Closed, with a note on how the area
was left; it can be Cancelled instead. A closed or cancelled permit is final.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime, time_diff_in_hours

from a3_constructa.hse import PRECAUTIONS, check_wbs, default_site, may_close_permit

MAX_HOURS = 24


class PermittoWork(Document):
	def validate(self):
		default_site(self)
		check_wbs(self)
		if self.is_new():
			self.issued_by = self.issued_by or frappe.session.user
			if not self.precautions:
				for p in PRECAUTIONS.get(self.permit_type, []):
					self.append("precautions", {"precaution": p})
		hours = time_diff_in_hours(self.valid_to, self.valid_from)
		if hours <= 0:
			frappe.throw(_("Valid To must be after Valid From."), title=_("Validity"))
		if hours > MAX_HOURS:
			frappe.throw(_("A permit runs for {0} hours at most; this one runs {1}. Issue a new permit for the next shift.").format(
				MAX_HOURS, f"{hours:g}"), title=_("Validity"))
		missing = [p.precaution for p in self.precautions if not p.confirmed]
		if self.status == "Open" and missing:
			frappe.throw(_("Every precaution must be in place before the permit is issued. Not yet: {0}.").format("; ".join(missing)),
			             title=_("Precautions"))
		self.status_change()

	def status_change(self):
		before = self.get_doc_before_save()
		was = before.status if before else "Open"
		if was in ("Closed", "Cancelled") and self.status != was:
			frappe.throw(_("This permit is {0}; issue a new one.").format(_(was).lower()), title=_("Permit"))
		if self.status != was and not may_close_permit(self):
			frappe.throw(_("Only the issuer ({0}) or a project manager can sign the permit off.").format(self.issued_by), title=_("Sign-off"))
		if self.status == "Closed" and was != "Closed":
			if not (self.closing_note or "").strip():
				frappe.throw(_("Say how the area was left in the Closing Note."), title=_("Sign-off"))
			self.closed_by, self.closed_on = frappe.session.user, now_datetime()
		if self.status == "Cancelled" and was != "Cancelled":
			self.closed_by, self.closed_on = frappe.session.user, now_datetime()

	@property
	def expired(self):
		return self.status == "Open" and get_datetime(self.valid_to) < now_datetime()


@frappe.whitelist()
def sign_off(name: str, status: str, note: str | None = None) -> str:
	"""Close or cancel a permit from the form's buttons."""
	if status not in ("Closed", "Cancelled"):
		frappe.throw(_("A permit is signed off as Closed or Cancelled."))
	doc = frappe.get_doc("Permit to Work", name)
	doc.check_permission("write")
	doc.status = status
	if note:
		doc.closing_note = note
	doc.save()
	return doc.status
