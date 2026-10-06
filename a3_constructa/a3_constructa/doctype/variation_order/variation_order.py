# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""A change the client asks for after the award: more work, less work, or different work.

It moves Draft → Submitted to Client → Approved or Rejected; an approved order
can still be Rejected (the client withdraws) or Cancelled. Only an Approved
variation counts:

- its value and time extension roll up onto the Awarded Quotation as the
  revised contract value and revised completion date;
- each line's amount goes onto the budget of its WBS (and cost code) through
  the Budget Revision Log (catalogue 3.5), so the WBS budget rises with an
  addition and falls with an omission.

Leaving Approved takes both back off. The log is kept in step on every save by
comparing what the order should hold on the budget with what it has already
written, so a correction to a line's WBS moves the budget as well.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from a3_constructa.a3_constructa.doctype.awarded_quotation.awarded_quotation import refresh_variation_totals
from a3_constructa.a3_constructa.doctype.budget_revision_log.budget_revision_log import logged_by_line, revise_budget

ALLOWED_MOVES = {
	"Draft": ("Submitted to Client", "Cancelled"),
	"Submitted to Client": ("Approved", "Rejected", "Draft"),
	"Approved": ("Rejected", "Cancelled"),
	"Rejected": ("Draft",),
	"Cancelled": (),
}
# A new order may start Draft or with the client; it is approved by moving it on.
START_STATUSES = ("Draft", "Submitted to Client")


class VariationOrder(Document):
	def validate(self):
		self.status = self.status or "Draft"
		self.validate_award()
		self.calculate_total()
		self.validate_sign()
		self.validate_status_move()
		self.validate_approved_lines()
		self.stamp_status_dates()

	def validate_award(self):
		award = frappe.db.get_value("Awarded Quotation", self.awarded_quotation, ["status", "project", "customer", "currency"], as_dict=True)
		if award and award.status == "Cancelled":
			frappe.throw(_("{0} is cancelled, so it cannot take a variation.").format(self.awarded_quotation))
		if award:
			self.project = self.project or award.project
			self.customer = self.customer or award.customer
			self.currency = self.currency or award.currency

	def calculate_total(self):
		total = 0.0
		for row in self.items:
			row.amount = flt(row.qty) * flt(row.rate)
			total += row.amount
		self.total_amount = total

	def validate_sign(self):
		"""An omission takes work out, so it has to reduce the contract value."""
		if self.variation_type == "Omission" and flt(self.total_amount) > 0:
			frappe.throw(_("An omission reduces the contract. Enter the omitted quantities as negative numbers."))

	def validate_status_move(self):
		before = self.get_doc_before_save()
		if not before:
			if self.status not in START_STATUSES and not self.flags.ignore_status_flow:
				frappe.throw(_("A new variation order starts as Draft or Submitted to Client; approve it by moving it on."))
			return
		if before.status == self.status:
			if self.status == "Approved" and self.amounts_changed(before):
				frappe.throw(_("{0} is approved, so its quantities and rates are fixed. Reject or cancel it and raise a new one.").format(self.name))
			return
		if self.status not in ALLOWED_MOVES.get(before.status, ()):
			frappe.throw(_("A variation order cannot go from {0} to {1}.").format(_(before.status), _(self.status)), title=_("Not allowed"))

	def amounts_changed(self, before):
		key = lambda rows: sorted((r.description, flt(r.qty), flt(r.rate)) for r in rows)
		return key(self.items) != key(before.items)

	def validate_approved_lines(self):
		"""The budget has to land somewhere: every line of an approved order needs a WBS."""
		if self.status != "Approved":
			return
		missing = [str(row.idx) for row in self.items if not row.wbs]
		if missing:
			frappe.throw(_("Give every line a WBS before approving, so its budget lands on the works (rows {0}).").format(", ".join(missing)),
			             title=_("WBS needed"))

	def stamp_status_dates(self):
		before = self.get_doc_before_save()
		moved_to = self.status if not before or before.status != self.status else None
		if moved_to == "Submitted to Client" and not self.submitted_date:
			self.submitted_date = today()
		if moved_to == "Approved":
			self.approved_date = self.approved_date or today()
			self.approved_by = self.approved_by or frappe.session.user
		if moved_to in ("Draft", "Rejected", "Cancelled") and before and before.status == "Approved":
			self.approved_by = None

	def on_update(self):
		refresh_variation_totals(self.awarded_quotation)
		previous = self.get_doc_before_save()
		if previous and previous.awarded_quotation != self.awarded_quotation:
			refresh_variation_totals(previous.awarded_quotation)
		sync_budget(self)

	def on_trash(self):
		if logged_by_line(self.project, [("Variation Order", self.name)]):
			frappe.throw(_("{0} has moved the budget. Cancel it instead of deleting it.").format(self.name))
		refresh_variation_totals(self.awarded_quotation, exclude=self.name)


def sync_budget(vo):
	"""Bring the Budget Revision Log in line with the order: its lines while it is
	Approved, nothing otherwise. Writes only the difference, per WBS and cost code."""
	if not vo.project:
		return
	want = defaultdict(float)
	if vo.status == "Approved":
		for row in vo.items:
			want[(row.wbs or None, row.cost_code or None)] += flt(row.amount)
	have = logged_by_line(vo.project, [("Variation Order", vo.name)])
	reason = _("{0}: {1}").format(_(vo.status), vo.subject)
	for key in sorted(set(want) | set(have), key=lambda k: (k[0] or "", k[1] or "")):
		delta = flt(want.get(key)) - flt(have.get(key))
		if abs(delta) >= 0.005:
			revise_budget(vo.project, key[0], key[1], delta, "Variation", vo, reason)
