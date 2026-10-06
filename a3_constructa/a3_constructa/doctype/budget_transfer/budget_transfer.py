# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money

from a3_constructa.a3_constructa.doctype.budget_revision_log.budget_revision_log import revise_budget
from a3_constructa.api.budget_allocation import wbs_budget, wbs_committed_and_actual


class BudgetTransfer(Document):
	"""Moves budget between WBS nodes and cost codes of one project (catalogue 1.6).

	Each line takes its amount off the From WBS and puts the same amount on the
	To WBS, so it nets to zero. A line can only move budget the From WBS has not
	already committed or spent. Submitting writes a Transfer Out and a Transfer In
	row to the Budget Revision Log; cancelling writes them back.
	"""

	def validate(self):
		if not self.company:
			self.company = frappe.db.get_value("Project", self.project, "company")
		self.validate_lines()
		self.check_available_budget()
		self.total_amount = sum(flt(row.amount) for row in self.items)

	def validate_lines(self):
		nodes = {row.from_wbs for row in self.items} | {row.to_wbs for row in self.items}
		projects = dict(frappe.get_all("WBS", filters={"name": ["in", list(nodes)]}, fields=["name", "project"], as_list=True))
		for row in self.items:
			if flt(row.amount) <= 0:
				frappe.throw(_("Row {0}: the amount to move must be more than zero.").format(row.idx))
			for field in ("from_wbs", "to_wbs"):
				if projects.get(row.get(field)) != self.project:
					frappe.throw(_("Row {0}: WBS {1} is not part of project {2}.").format(row.idx, frappe.bold(row.get(field)), self.project))
			if row.from_wbs == row.to_wbs and (row.from_cost_code or "") == (row.to_cost_code or ""):
				frappe.throw(_("Row {0}: From and To are the same WBS and cost code, so nothing would move.").format(row.idx))

	def check_available_budget(self):
		"""A line may not move more than the From WBS's budget less its committed and actual cost."""
		asked = {}
		for row in self.items:
			key = (row.from_wbs, row.from_cost_code or None)
			asked[key] = asked.get(key, 0) + flt(row.amount)

		currency = frappe.get_cached_value("Company", self.company, "default_currency") if self.company else None
		money = lambda v: fmt_money(v, currency=currency)
		for (wbs, cost_code), amount in asked.items():
			budget = wbs_budget(self.project, wbs, cost_code)
			committed, actual = wbs_committed_and_actual(self.project, wbs, cost_code)
			available = budget - committed - actual
			for row in self.items:
				if (row.from_wbs, row.from_cost_code or None) == (wbs, cost_code):
					row.available_budget = available
			if amount > available + 0.005:
				where = frappe.bold(wbs) + (f" / {cost_code}" if cost_code else "")
				frappe.throw(
					_("{0} has a budget of {1}, with {2} committed and {3} spent, so {4} can be moved. This transfer moves {5}.").format(
						where, money(budget), money(committed), money(actual), frappe.bold(money(max(available, 0))), money(amount)
					),
					title=_("Not enough budget to move"),
				)

	def on_submit(self):
		self.write_log()

	def on_cancel(self):
		self.write_log(cancel=True)

	def write_log(self, cancel=False):
		sign = -1 if cancel else 1
		note = (_("Cancelled: {0}") if cancel else "{0}").format(self.reason)
		for row in self.items:
			revise_budget(self.project, row.from_wbs, row.from_cost_code, -sign * flt(row.amount), "Transfer Out", self, note)
			revise_budget(self.project, row.to_wbs, row.to_cost_code, sign * flt(row.amount), "Transfer In", self, note)


@frappe.whitelist()
def get_available_budget(project, wbs, cost_code=None):
	"""For the form: what the From WBS (and cost code) can give away."""
	frappe.has_permission("Budget Transfer", "create", throw=True)
	budget = wbs_budget(project, wbs, cost_code or None)
	committed, actual = wbs_committed_and_actual(project, wbs, cost_code or None)
	return {"budget": budget, "committed": committed, "actual": actual, "available": budget - committed - actual}
