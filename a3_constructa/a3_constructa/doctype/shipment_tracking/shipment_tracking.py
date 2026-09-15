# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt


class ShipmentTracking(Document):
	def validate(self):
		self.set_transit_days()
		self.set_milestone_variance()
		self.validate_dates()

	def set_transit_days(self):
		"""Build sheet head 39 row 11: transit_days = ata_discharge - etd_origin.

		Only meaningful once the vessel has actually arrived, so a shipment still
		at sea shows nothing rather than a count measured against today.
		"""
		if self.etd_origin and self.ata_discharge:
			self.transit_days = date_diff(self.ata_discharge, self.etd_origin)
		else:
			self.transit_days = 0

	def set_milestone_variance(self):
		"""Days late against plan, per milestone. Positive means late."""
		for row in self.milestones:
			if row.planned_date and row.actual_date:
				row.variance_days = date_diff(row.actual_date, row.planned_date)
			else:
				row.variance_days = 0

	def validate_dates(self):
		"""Catch the date orderings that make the TAT and demurrage reports wrong."""
		if self.etd_origin and self.ata_discharge and \
				date_diff(self.ata_discharge, self.etd_origin) < 0:
			frappe.throw(_("Arrival at discharge port cannot be before departure from origin."))

		if self.period_pairs_invalid():
			frappe.throw(_("Inland arrival cannot be before inland despatch."))

	def period_pairs_invalid(self) -> bool:
		return bool(
			self.inland_despatch_date
			and self.inland_arrival_date
			and date_diff(self.inland_arrival_date, self.inland_despatch_date) < 0
		)

	def before_submit(self):
		"""Row 21: a blocking Mandatory Document Rule holds up an import.

		The rule lists the documents a shipment of this type must carry; if it is
		marked blocking, the shipment cannot be submitted until each of them is
		present with its original received.
		"""
		self.check_mandatory_documents()

	def check_mandatory_documents(self):
		rules = frappe.get_all(
			"Mandatory Document Rule",
			filters={"reference_doctype": self.doctype, "is_blocking": 1},
			pluck="name",
		)
		if not rules:
			return

		present = {
			row.document_type for row in self.documents
			if row.document_type and row.is_original_received
		}

		missing = []
		for rule_name in rules:
			rule = frappe.get_doc("Mandatory Document Rule", rule_name)
			# A rule scoped to a transaction type only applies to that type.
			if rule.transaction_type and rule.transaction_type != self.shipment_type:
				continue
			for row in rule.document_type:
				if row.document_type not in present:
					missing.append(row.document_type)

		if missing:
			frappe.throw(
				_("These documents are mandatory and not yet received: {0}").format(
					", ".join(sorted(set(missing)))
				)
			)
