# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""A contract the client has awarded to us.

The award is where a job starts on the client side: what was won, from whom,
for how much, and by when. Its components are the packages of work it covers,
each priced in detail by a BOQ; its milestones are the programme the client
holds us to. Variation Orders and Deliverables hang off it.

It is saved, not submitted, because the programme keeps moving while the works
run: actual dates, progress and the revised figures change for months after the
award itself is fixed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, date_diff, flt

# Statuses a job is live in. The dashboard and the "past completion" checks
# count only these.
ACTIVE_STATUSES = ("Awarded", "In Progress", "On Hold")


class AwardedQuotation(Document):
	def validate(self):
		self.set_company_defaults()
		self.validate_dates()
		self.calculate_contract_value()
		self.validate_component_boqs()
		self.update_milestones()
		self.set_variation_totals()

	def set_company_defaults(self):
		if not self.currency and self.company:
			self.currency = frappe.get_cached_value("Company", self.company, "default_currency")

	def validate_dates(self):
		if self.start_date and self.end_date and date_diff(self.end_date, self.start_date) < 0:
			frappe.throw(_("The completion date cannot be before the start date."))

	def calculate_contract_value(self):
		"""The contract value is the sum of its components, so the two can never disagree."""
		total = 0.0
		for row in self.components:
			row.amount = flt(row.qty) * flt(row.rate)
			total += row.amount
		self.contract_value = total

	def validate_component_boqs(self):
		"""A component's BOQ has to price this award's project, and no other award."""
		for row in self.components:
			if not row.boq:
				continue
			boq_project, boq_award, stage = frappe.db.get_value("BOQ", row.boq, ["project", "awarded_quotation", "boq_stage"])
			# A tender BOQ priced the bid before there was a project (P-03C).
			if self.project and stage != "Tender" and boq_project != self.project:
				frappe.throw(
					_("Row {0}: BOQ {1} is for project {2}, not {3}.").format(
						row.idx, row.boq, boq_project, self.project
					)
				)
			if boq_award and boq_award != self.name:
				frappe.throw(_("Row {0}: BOQ {1} already prices {2}.").format(row.idx, row.boq, boq_award))

	def on_update(self):
		self.link_component_boqs()
		# The programme sets the payment schedule of the award's submitted orders.
		from a3_constructa.api.milestone_billing import sync_submitted_orders

		sync_submitted_orders(self)

	def link_component_boqs(self):
		"""Point each component's BOQ back at this award.

		A BOQ and an award can be linked from either side: a component names its
		BOQ, and a BOQ created from the award names the award. Writing the back
		link keeps the award's Connections tab and the overview's checks agreeing
		with the components table.
		"""
		for boq in {row.boq for row in self.components if row.boq}:
			if not frappe.db.get_value("BOQ", boq, "awarded_quotation"):
				frappe.db.set_value("BOQ", boq, "awarded_quotation", self.name, update_modified=False)

	def update_milestones(self):
		"""Derive each milestone's variance and the award's progress.

		An actual end date is the evidence that a milestone is done, so entering
		one completes it, and Completed without one is refused. Progress is the
		weightage of completed milestones; when no weightage has been entered it
		falls back to the share of milestones completed.
		"""
		total_weight = completed_weight = total_billing = 0.0
		completed = 0

		for row in self.milestones:
			if row.planned_start and row.planned_end and date_diff(row.planned_end, row.planned_start) < 0:
				frappe.throw(_("Row {0}: {1} ends before it starts.").format(row.idx, frappe.bold(row.milestone)))
			if row.actual_end:
				row.status = "Completed"
			elif row.status == "Completed":
				frappe.throw(
					_("Row {0}: enter the actual end date of {1} before marking it Completed.").format(
						row.idx, frappe.bold(row.milestone)
					)
				)

			row.variance_days = date_diff(row.actual_end, row.planned_end) if row.actual_end else 0

			total_weight += flt(row.weightage)
			total_billing += flt(row.billing_percent)
			if row.status == "Completed":
				completed += 1
				completed_weight += flt(row.weightage)

		# Catalogue 4.2: a completed milestone's billing % falls due on an award billed by milestones.
		from a3_constructa.api.milestone_billing import is_due

		components = {c.component for c in self.components}
		for row in self.milestones:
			if row.component and row.component not in components:
				frappe.throw(_("Row {0}: {1} is not a component of this award.").format(row.idx, frappe.bold(row.component)))
			row.billing_due = int(is_due(self, row))

		if total_weight > 100:
			frappe.throw(_("Milestone weightage adds up to {0}%. It cannot be more than 100%.").format(total_weight))
		if total_billing > 100:
			frappe.throw(_("Milestone billing adds up to {0}%. It cannot be more than 100%.").format(total_billing))

		if total_weight:
			self.progress_percent = completed_weight / total_weight * 100
		else:
			self.progress_percent = completed / len(self.milestones) * 100 if self.milestones else 0

	def set_variation_totals(self):
		award = None if self.is_new() else self.name
		self.update(get_variation_totals(award, self.contract_value, self.end_date))


def get_variation_totals(award: str | None, contract_value, end_date, exclude: str | None = None) -> dict:
	"""Revised value and completion date: the award plus its approved Variation Orders."""
	amount = days = 0
	if award:
		filters = {"awarded_quotation": award, "status": "Approved"}
		if exclude:
			filters["name"] = ["!=", exclude]
		for vo in frappe.get_all("Variation Order", filters=filters, fields=["total_amount", "time_extension_days"]):
			amount += flt(vo.total_amount)
			days += cint(vo.time_extension_days)

	return {
		"approved_variations": amount,
		"revised_contract_value": flt(contract_value) + amount,
		"time_extension_days": days,
		"revised_end_date": add_days(end_date, days) if end_date else None,
	}


def refresh_variation_totals(award: str | None, exclude: str | None = None):
	"""Write the revised figures onto an award after one of its Variation Orders changes.

	Uses db_set rather than a full save so a variation can be approved by someone
	who may not edit the award itself.
	"""
	if not award or not frappe.db.exists("Awarded Quotation", award):
		return
	contract_value, end_date = frappe.db.get_value("Awarded Quotation", award, ["contract_value", "end_date"])
	frappe.db.set_value(
		"Awarded Quotation",
		award,
		get_variation_totals(award, contract_value, end_date, exclude=exclude),
		update_modified=False,
	)
