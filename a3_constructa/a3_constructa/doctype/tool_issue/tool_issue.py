# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

# Head 55 keeps small tools as serialised stock rather than Assets, so custody
# is a warehouse balance: issuing a tool moves it from the store to the holder's
# custody warehouse, and it stays on the books until it comes back.
ISSUE_ENTRY_TYPE = "Tool Issue"
RETURN_ENTRY_TYPE = "Tool Return"


class ToolIssue(Document):
	def validate(self):
		self.set_valuation_rates()
		self.set_status()
		self.validate_returns()

	def set_valuation_rates(self):
		"""What the tool is worth, for the outstanding and loss reports.

		Taken once at issue and then left alone: a tool lost six months later is
		recovered at what it was worth when handed over, not at today's rate.
		"""
		for row in self.items:
			if row.valuation_rate or not row.item_code:
				continue
			row.valuation_rate = flt(
				frappe.db.get_value("Bin",
				                    {"item_code": row.item_code, "warehouse": self.from_warehouse},
				                    "valuation_rate")
			) or flt(frappe.db.get_value("Item", row.item_code, "valuation_rate"))

	def validate_returns(self):
		for row in self.items:
			if flt(row.returned_qty) > flt(row.qty):
				frappe.throw(
					_("Row {0}: returned quantity {1} is more than the {2} issued.").format(
						row.idx, flt(row.returned_qty), flt(row.qty))
				)
			# Keep the flag and the quantity agreeing, whichever the user set.
			if row.is_returned and not flt(row.returned_qty):
				row.returned_qty = flt(row.qty)
			if flt(row.returned_qty) >= flt(row.qty) and flt(row.qty):
				row.is_returned = 1
				if not row.return_date:
					row.return_date = nowdate()

	def set_status(self):
		"""Derive the issue status from the lines.

		Lost, Damaged and Written Off are set by hand on the lines' condition and
		are not overwritten here; everything else follows what has come back.
		"""
		if self.status in ("Lost", "Damaged", "Written Off"):
			return

		issued = sum(flt(r.qty) for r in self.items)
		returned = sum(flt(r.returned_qty) for r in self.items)

		if not issued or not returned:
			self.status = "Issued"
		elif returned >= issued:
			self.status = "Returned"
		else:
			self.status = "Partially Returned"

	def on_submit(self):
		self.make_stock_entry()

	def make_stock_entry(self):
		"""Move the tools into the holder's custody warehouse.

		Row 25: the issue posts stock rather than only recording an intention, so
		a tool in someone's hands still shows on the books - in their custody
		warehouse rather than the store.
		"""
		if self.stock_entry:
			return

		entry = frappe.new_doc("Stock Entry")
		entry.stock_entry_type = ISSUE_ENTRY_TYPE
		entry.purpose = "Material Transfer"
		# set_posting_time is what makes ERPNext honour the date given; without
		# it the movement is stamped today, so a tool issued last week would
		# leave the store today and any earlier return would be backdated
		# against it.
		entry.posting_date = self.issue_date
		entry.set_posting_time = 1
		entry.project = self.project
		entry.a3c_tool_issue = self.name

		for row in self.items:
			item = {
				"item_code": row.item_code,
				"qty": flt(row.qty),
				"uom": row.uom,
				"s_warehouse": self.from_warehouse,
				"t_warehouse": self.to_warehouse,
				"basic_rate": flt(row.valuation_rate),
			}
			if row.serial_no:
				item["serial_no"] = row.serial_no
			entry.append("items", item)

		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()

		self.db_set("stock_entry", entry.name)

	def on_cancel(self):
		"""Cancelling the issue must take the stock movement with it."""
		self.ignore_linked_doctypes = ("Stock Entry",)

		if self.stock_entry:
			entry = frappe.get_doc("Stock Entry", self.stock_entry)
			if entry.docstatus == 1:
				entry.flags.ignore_permissions = True
				entry.cancel()
		self.db_set("status", "Issued")
