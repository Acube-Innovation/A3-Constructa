# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

from a3_constructa.a3_constructa.doctype.budget_revision_log.budget_revision_log import logged_by_line, revise_budget


class BOQ(Document):
	def validate(self):
		self.validate_stage()
		self.set_revision()
		self.sync_contingency()
		self.validate_allowance_lines()
		self.calculate_amounts()
		self.calculate_pricing()

	def sync_contingency(self):
		"""Catalogue 2.6: the contingency lives as one allowance line, kept to the
		header's amount, so it is in the BOQ total but never allocated to the works."""
		rows = [row for row in self.items if row.is_contingency]
		amount = flt(self.contingency_amount)
		if amount < 0:
			frappe.throw(_("Contingency cannot be negative."))
		if not amount:
			for row in rows:
				self.remove(row)
			return
		row = rows[0] if rows else self.append("items", {"is_allowance": 1, "is_contingency": 1})
		for extra in rows[1:]:
			self.remove(extra)
		row.update({"is_allowance": 1, "description": _("Contingency"), "amount": amount, "cost_head": row.cost_head or self.cost_head,
		            "boq_ref": row.boq_ref or _("CONT")})

	def calculate_pricing(self):
		"""Catalogue 2.6: from cost to selling price.

		Cost: priced lines at their estimate's cost rate × qty, plus allowance lines
		at their amount (preliminaries among them); lines that draw from an
		allowance are inside it, so they are not counted again. Selling: cost ×
		(1 + overhead + profit + risk), plus the contingency at face value. Margin
		is the markup's share of the selling price; the contingency is neither cost
		nor margin.
		"""
		for field in ("overhead_percent", "profit_percent", "risk_percent"):
			if flt(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(self.meta.get_label(field)))
		markup = (flt(self.overhead_percent) + flt(self.profit_percent) + flt(self.risk_percent)) / 100
		factor = 1 + markup
		prelim_heads = preliminaries_heads()

		cost = preliminaries = 0.0
		unpriced = 0
		for row in self.items:
			if row.is_contingency:
				row.selling_rate, row.margin_percent = flt(row.amount), 0
				continue
			if row.is_allowance:
				cost += flt(row.amount)
				if row.cost_head in prelim_heads:
					preliminaries += flt(row.amount)
				row.selling_rate = flt(row.amount) * factor
			else:
				row.selling_rate = flt(row.cost_rate) * factor
				if not row.draws_from_allowance:
					cost += flt(row.cost_rate) * flt(row.boq_qty)
					if not flt(row.cost_rate):
						unpriced += 1
			row.margin_percent = markup / factor * 100 if flt(row.selling_rate) else 0

		self.cost_total = cost
		self.preliminaries_total = preliminaries
		self.unpriced_lines = unpriced
		self.overhead_amount = cost * flt(self.overhead_percent) / 100
		self.profit_amount = cost * flt(self.profit_percent) / 100
		self.risk_amount = cost * flt(self.risk_percent) / 100
		self.selling_total = cost * factor + flt(self.contingency_amount)
		markup_amount = self.overhead_amount + self.profit_amount + self.risk_amount
		self.margin_percent = markup_amount / self.selling_total * 100 if self.selling_total else 0

	def validate_stage(self):
		"""Catalogue 2.4: a Tender BOQ is the client's bill priced for a bid, before
		there is a project; a Contract or Budget BOQ belongs to a project."""
		self.boq_stage = self.boq_stage or "Budget"
		if self.boq_stage != "Tender" and not self.project:
			frappe.throw(_("A {0} BOQ needs a project.").format(_(self.boq_stage)))
		if self.opportunity and not self.customer:
			opp = frappe.db.get_value("Opportunity", self.opportunity, ["opportunity_from", "party_name"], as_dict=True)
			if opp and opp.opportunity_from == "Customer":
				self.customer = opp.party_name

	def before_submit(self):
		# A tender is priced and sent through its quotation (P-02E). Approving it
		# here would write it to the budget, which only Contract and Budget BOQs carry.
		if self.boq_stage == "Tender":
			frappe.throw(
				_("A Tender BOQ is not approved as a budget. Price it and send it through a Quotation; "
				  "once the work is won it becomes the Contract BOQ."),
				title=_("Tender BOQ"),
			)

	def set_revision(self):
		"""Catalogue 1.6: an amendment is the next revision and must say why."""
		if not self.amended_from:
			return
		self.revision_no = (frappe.db.get_value("BOQ", self.amended_from, "revision_no") or 0) + 1
		if not (self.revision_reason or "").strip():
			frappe.throw(_("Say why the BOQ is being revised (Revision Reason)."), title=_("Revision reason needed"))

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
			elif not row.item_code and self.boq_stage != "Tender":
				frappe.throw(_("Row {0}: pick the item, or tick Allowance for a provisional sum.").format(row.idx))
			elif not row.item_code and not (row.description or "").strip():
				frappe.throw(_("Row {0}: a tender line without an item needs its description from the bill.").format(row.idx))
			elif not row.item_code:
				# The bill's wording stands in for the item name, so the lines grid shows it.
				row.item_name = (row.description or "")[:140]
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
		self.log_budget()

	def on_cancel(self):
		self.db_set("status", "Rejected")
		self.log_budget(cancel=True)

	def budget_by_line(self):
		"""Approved budget per (wbs, cost code). Allowance lines carry what is left
		of the allowance, so the sum is the BOQ's approved budget, counted once."""
		out = {}
		for row in self.items:
			key = (row.wbs, row.cost_code)
			out[key] = out.get(key, 0) + flt(row.budget_amount)
		return out

	def revision_chain(self):
		"""This BOQ's earlier revisions, newest first."""
		chain, name = [], self.amended_from
		while name and name not in chain:
			chain.append(name)
			name = frappe.db.get_value("BOQ", name, "amended_from")
		return chain

	def log_budget(self, cancel=False, posted_on=None, posted_by=None):
		"""Write this BOQ's budget to the Budget Revision Log.

		A first BOQ writes its lines as Original. A revision writes the change
		against what its earlier revisions still hold in the log; that is the full
		difference to the revision it amends, since cancelling that revision took
		its lines back out. Cancelling a BOQ takes its own lines back out.
		"""
		if cancel:
			held = logged_by_line(self.project, [("BOQ", self.name)])
			for (wbs, cost_code), amount in held.items():
				revise_budget(self.project, wbs, cost_code, -amount, "BOQ Revision", self,
				              _("BOQ {0} cancelled").format(self.name), posted_on, posted_by)
			return

		if not self.amended_from:
			for (wbs, cost_code), amount in self.budget_by_line().items():
				revise_budget(self.project, wbs, cost_code, amount, "Original", self,
				              _("BOQ {0} approved").format(self.name), posted_on, posted_by)
			return

		before = logged_by_line(self.project, [("BOQ", n) for n in self.revision_chain()])
		now = self.budget_by_line()
		reason = _("Revision {0}: {1}").format(self.revision_no, self.revision_reason)
		for key in sorted(set(before) | set(now), key=lambda k: (k[0] or "", k[1] or "")):
			revise_budget(self.project, key[0], key[1], flt(now.get(key)) - flt(before.get(key)), "BOQ Revision",
			              self, reason, posted_on, posted_by)


def drawn_value(row):
	"""What an item line spends of its allowance: its approved value once it has
	approved figures, its estimate before that."""
	return flt(row.budget_amount) if flt(row.approved_qty) else flt(row.amount)


def preliminaries_heads():
	"""Cost heads flagged Preliminaries, with every cost head below them."""
	heads = set()
	for top in frappe.get_all("Cost Head", filters={"is_preliminaries": 1}, fields=["name", "lft", "rgt"]):
		heads.update(frappe.get_all("Cost Head", filters={"lft": [">=", top.lft], "rgt": ["<=", top.rgt]}, pluck="name"))
	return heads


def refresh_pricing(boq: str):
	"""Recompute a draft BOQ's selling figures after a line's cost rate changed on
	its Estimate Sheet, without a full save of the BOQ."""
	doc = frappe.get_doc("BOQ", boq)
	if doc.docstatus != 0:
		return
	doc.calculate_pricing()
	for row in doc.items:
		row.db_set({"selling_rate": row.selling_rate, "margin_percent": row.margin_percent}, update_modified=False)
	doc.db_set({field: doc.get(field) for field in (
		"cost_total", "preliminaries_total", "unpriced_lines", "overhead_amount", "profit_amount", "risk_amount",
		"selling_total", "margin_percent")}, update_modified=False)
