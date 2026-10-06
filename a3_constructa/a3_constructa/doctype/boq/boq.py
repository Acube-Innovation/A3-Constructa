# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money


class BOQ(Document):
	def validate(self):
		self.validate_allowance_lines()
		self.calculate_amounts()

	def calculate_amounts(self):
		"""Build sheet head 17 row 5 and head 18: amount and budget_amount are derived.

		`amount` is the BOQ line value (qty x rate); `budget_amount` is the same
		arithmetic on the approved figures, which is what the Budget doctype and
		the Budget vs WBS report read. Both are read-only on the form, so they are
		computed here rather than trusted from the client.

		Catalogue 1.4: an allowance line has no item; its amount is entered. The
		item lines that draw from it spend it, so the allowance's budget_amount is
		only what they have not spent (allowance_remaining). That keeps every sum
		of budget_amount over a BOQ right: the drawn lines are counted once, as
		themselves, and the rest of the allowance once, on the allowance line.
		The BOQ total counts the allowance in full and leaves out the lines inside it.
		"""
		for row in self.items:
			if not row.is_allowance:
				row.amount = flt(row.boq_qty) * flt(row.rate)
				row.budget_amount = flt(row.approved_qty) * flt(row.approved_rate)

		used = {}
		for row in self.items:
			if row.draws_from_allowance:
				used[row.draws_from_allowance] = used.get(row.draws_from_allowance, 0) + drawn_value(row)

		total = 0.0
		for row in self.items:
			if row.is_allowance:
				row.allowance_used = used.get(row.name, 0)
				row.allowance_remaining = flt(row.amount) - flt(row.allowance_used)
				if row.allowance_remaining < -0.005:
					frappe.throw(
						_("Row {0}: allowance {1} is {2}, but the lines drawing from it come to {3}. Raise the allowance or reduce those lines.").format(
							row.idx,
							frappe.bold(row.description or row.name),
							fmt_money(row.amount, currency=self.currency),
							fmt_money(row.allowance_used, currency=self.currency),
						),
						title=_("Allowance overdrawn"),
					)
				row.budget_amount = row.allowance_remaining
			else:
				row.allowance_used = row.allowance_remaining = 0
			if not row.draws_from_allowance:
				total += flt(row.amount)

		self.total_amount = total

	def validate_allowance_lines(self):
		allowances = {row.name for row in self.items if row.is_allowance}
		self.remap_copied_references(allowances)
		for row in self.items:
			if row.is_allowance:
				row.draws_from_allowance = None
				if not row.description:
					frappe.throw(_("Row {0}: describe the allowance, for example 'PC sum: lobby feature wall'.").format(row.idx))
				if flt(row.amount) <= 0:
					frappe.throw(_("Row {0}: enter the allowance amount.").format(row.idx))
				# An allowance has no item, so nothing is bought or measured against a quantity.
				# Its description stands in for the item name so the lines grid shows it.
				row.item_code = None
				row.item_name = (row.description or "")[:140]
				row.boq_qty = row.rate = row.approved_qty = row.approved_rate = 0
			elif not row.item_code:
				frappe.throw(_("Row {0}: pick the item, or tick Allowance for a provisional sum.").format(row.idx))
			elif row.draws_from_allowance and row.draws_from_allowance not in allowances:
				frappe.throw(
					_("Row {0}: {1} is not an allowance line of this BOQ. Pick the allowance again; if it is new, save the BOQ first.").format(
						row.idx, row.draws_from_allowance
					)
				)

	def remap_copied_references(self, allowances):
		"""An amended or duplicated BOQ gets new row names, so a line still points
		at the allowance row of the BOQ it was copied from. Point it at the row in
		the same position here."""
		by_idx = {row.idx: row.name for row in self.items if row.is_allowance}
		for row in self.items:
			ref = row.draws_from_allowance
			if not ref or ref in allowances:
				continue
			idx = frappe.db.get_value("BOQ Item", {"name": ref, "parenttype": "BOQ"}, "idx")
			if idx in by_idx:
				row.draws_from_allowance = by_idx[idx]

	def on_submit(self):
		# The workflow drives `status`; this only covers a submit made without one.
		if self.status not in ("Approved", "Rejected"):
			self.db_set("status", "Approved")

	def on_cancel(self):
		self.db_set("status", "Rejected")


def drawn_value(row):
	"""What an item line spends of its allowance: its approved value once it has
	approved figures, its estimate before that."""
	return flt(row.budget_amount) if flt(row.approved_qty) else flt(row.amount)
