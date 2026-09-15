# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class WBSAllocation(Document):
	def validate(self):
		self.calculate_amounts()
		self.set_balance_qty()

	def calculate_amounts(self):
		for row in self.items:
			row.allocated_amount = flt(row.allocated_qty) * flt(row.rate)

	def set_balance_qty(self):
		"""How much of each BOQ line is still unallocated.

		The balance is against the BOQ line, not this document, so it counts
		every allocation of that line except the rows being saved here - saving
		the same allocation twice must not double-count it.
		"""
		if not self.boq:
			for row in self.items:
				row.balance_qty = 0
			return

		for row in self.items:
			if not row.boq_item:
				row.balance_qty = 0
				continue

			boq_qty = flt(frappe.db.get_value("BOQ Item", row.boq_item, "boq_qty"))

			allocated_elsewhere = frappe.db.sql(
				"""
				select sum(item.allocated_qty)
				from `tabWBS Allocation Item` item
				inner join `tabWBS Allocation` alloc on alloc.name = item.parent
				where item.boq_item = %(boq_item)s
				  and alloc.name != %(this)s
				  and alloc.docstatus < 2
				""",
				{"boq_item": row.boq_item, "this": self.name or ""},
			)[0][0]

			row.balance_qty = boq_qty - flt(allocated_elsewhere) - flt(row.allocated_qty)
