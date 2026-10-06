# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Estimate Sheet - catalogue 2.5: the rate of one BOQ line, built up from resources.

Each resource is priced per unit of the BOQ line:

- material, subcontract and other: qty per BOQ unit × (1 + wastage) × rate,
  wastage counting for materials only;
- labour and equipment: day rate ÷ output per day (BOQ units a day).

The sum is the line's unit cost, written to the BOQ line's cost_rate on save.
"Fetch prices" fills each item's rate from the buying price list, else the
latest submitted supplier quotation, and a freight line from the freight rate
contract; it records where each rate came from. A rate typed by hand
(source Manual) is never overwritten.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

from a3_constructa.a3_constructa.doctype.boq.boq import refresh_pricing

PER_DAY = ("Labour", "Equipment")


class EstimateSheet(Document):
	def validate(self):
		self.validate_line()
		self.calculate()

	def validate_line(self):
		line = frappe.db.get_value(
			"BOQ Item", {"name": self.boq_item, "parent": self.boq, "parenttype": "BOQ"},
			["idx", "boq_ref", "cost_head", "description", "item_name", "uom", "boq_qty", "is_allowance"], as_dict=True,
		)
		if not line:
			frappe.throw(_("That line is not part of BOQ {0}. Open the estimate from the BOQ line itself.").format(self.boq))
		if line.is_allowance:
			frappe.throw(_("Line {0} of {1} is an allowance; an allowance is a sum, not built up from resources.").format(
				line.boq_ref or line.idx, self.boq))
		other = frappe.db.get_value("Estimate Sheet", {"boq": self.boq, "boq_item": self.boq_item, "name": ["!=", self.name]})
		if other:
			frappe.throw(_("BOQ line {0} already has Estimate Sheet {1}.").format(line.boq_ref or self.boq_item, other))
		self.boq_ref = line.boq_ref
		self.cost_head = line.cost_head
		self.description = line.description or line.item_name
		self.uom = line.uom
		self.boq_qty = line.boq_qty
		self.currency = self.currency or frappe.db.get_value("BOQ", self.boq, "currency")
		self.title = " · ".join(x for x in (self.boq_ref, (self.description or "")[:80]) if x)

	def calculate(self):
		totals = {t: 0.0 for t in ("Material", "Labour", "Equipment", "Subcontract", "Other")}
		for row in self.resources:
			if row.resource_type in PER_DAY:
				row.cost_per_unit = flt(row.rate) / flt(row.output_per_day) if flt(row.output_per_day) else 0
			else:
				wastage = flt(row.wastage_percent) if row.resource_type == "Material" else 0
				row.cost_per_unit = flt(row.qty_per_unit) * (1 + wastage / 100) * flt(row.rate)
			totals[row.resource_type] += flt(row.cost_per_unit)
		self.material_cost = totals["Material"]
		self.labour_cost = totals["Labour"]
		self.equipment_cost = totals["Equipment"]
		self.subcontract_cost = totals["Subcontract"]
		self.other_cost = totals["Other"]
		self.unit_cost = sum(totals.values())
		self.total_cost = self.unit_cost * flt(self.boq_qty)

	def on_update(self):
		frappe.db.set_value("BOQ Item", self.boq_item, {"cost_rate": self.unit_cost, "estimate_sheet": self.name}, update_modified=False)
		refresh_pricing(self.boq)

	def on_trash(self):
		frappe.db.set_value("BOQ Item", self.boq_item, {"cost_rate": 0, "estimate_sheet": None}, update_modified=False)
		refresh_pricing(self.boq)

	@frappe.whitelist()
	def fetch_prices(self):
		"""Fill rates from their sources; leave hand-typed (Manual) rates alone."""
		company = self.company()
		for row in self.resources:
			if row.rate_source == "Manual" and flt(row.rate):
				continue
			found = price_for(row, self.currency, company)
			if found:
				row.rate, row.rate_source, row.source_doctype, row.source_reference = found["rate"], found["source"], found["doctype"], found["name"]
				if not row.uom and found.get("uom"):
					row.uom = found["uom"]
		self.calculate()

	def company(self):
		project = frappe.db.get_value("BOQ", self.boq, "project")
		return (frappe.db.get_value("Project", project, "company") if project else None) or frappe.defaults.get_user_default("Company")


def price_for(row, currency, company):
	"""The rate for one resource and where it came from, or None."""
	if row.item_code:
		price_list = frappe.db.get_single_value("Buying Settings", "buying_price_list")
		if price_list and frappe.db.get_value("Price List", price_list, "currency") == currency:
			uoms = [u for u in (row.uom, frappe.get_cached_value("Item", row.item_code, "stock_uom")) if u]
			for uom in uoms:
				price = frappe.db.get_value("Item Price", {"item_code": row.item_code, "price_list": price_list, "uom": uom},
				                            ["name", "price_list_rate"], as_dict=True, order_by="valid_from desc")
				if price:
					return {"rate": price.price_list_rate, "source": "Price List", "doctype": "Price List", "name": price_list, "uom": uom}

		company_currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
		for q in frappe.db.sql(
			"""
			select sq.name, sq.currency, sqi.rate, sqi.base_rate, sqi.uom
			from `tabSupplier Quotation Item` sqi
			inner join `tabSupplier Quotation` sq on sq.name = sqi.parent
			where sq.docstatus = 1 and sqi.item_code = %(item)s and (%(company)s is null or sq.company = %(company)s)
			order by sq.transaction_date desc, sq.creation desc, sq.name desc
			""",
			{"item": row.item_code, "company": company},
			as_dict=True,
		):
			if row.uom and q.uom != row.uom:
				continue
			if q.currency == currency:
				rate = q.rate
			elif currency == company_currency:
				rate = q.base_rate
			else:
				continue
			return {"rate": rate, "source": "Supplier Quotation", "doctype": "Supplier Quotation", "name": q.name, "uom": q.uom}
		return None

	if row.rate_source == "Freight Rate Contract":
		# A freight contract prices a container on a route; the row's qty per unit
		# says how many containers one BOQ unit takes.
		if row.source_reference and row.source_doctype == "Freight Rate Contract":
			contract = frappe.db.get_value("Freight Rate Contract", row.source_reference, ["name", "rate", "currency", "status", "valid_to"], as_dict=True)
		else:
			contract = frappe.db.get_value(
				"Freight Rate Contract",
				{"status": "Active", "currency": currency, "valid_from": ["<=", today()], "valid_to": [">=", today()]},
				["name", "rate", "currency", "status", "valid_to"], as_dict=True, order_by="rate asc",
			)
		if contract and contract.currency == currency and contract.status == "Active" and (not contract.valid_to or getdate(contract.valid_to) >= getdate(today())):
			return {"rate": contract.rate, "source": "Freight Rate Contract", "doctype": "Freight Rate Contract", "name": contract.name}
	return None


@frappe.whitelist()
def open_for_line(boq: str, boq_item: str) -> str:
	"""The line's Estimate Sheet, created (with a first resource for its item) if it has none."""
	frappe.has_permission("Estimate Sheet", "create", throw=True)
	existing = frappe.db.get_value("Estimate Sheet", {"boq": boq, "boq_item": boq_item})
	if existing:
		return existing
	line = frappe.db.get_value("BOQ Item", {"name": boq_item, "parent": boq}, ["item_code", "uom"], as_dict=True)
	if not line:
		frappe.throw(_("Save the BOQ first, so the line can be priced."))
	sheet = frappe.new_doc("Estimate Sheet")
	sheet.boq, sheet.boq_item = boq, boq_item
	if line.item_code:
		sheet.append("resources", {"resource_type": "Material", "item_code": line.item_code, "uom": line.uom, "qty_per_unit": 1,
		                           "description": frappe.get_cached_value("Item", line.item_code, "item_name"), "rate_source": "Price List"})
		sheet.fetch_prices()
	sheet.insert()
	return sheet.name


@frappe.whitelist()
def reprice_sheets(boq: str) -> list[dict]:
	"""Fetch prices again on every sheet of an open (draft) BOQ; return what changed."""
	frappe.has_permission("Estimate Sheet", "write", throw=True)
	if frappe.db.get_value("BOQ", boq, "docstatus") != 0:
		frappe.throw(_("{0} is approved; its estimates are closed.").format(boq))
	changes = []
	for name in frappe.get_all("Estimate Sheet", filters={"boq": boq}, pluck="name", order_by="boq_ref"):
		sheet = frappe.get_doc("Estimate Sheet", name)
		before = flt(sheet.unit_cost)
		sheet.fetch_prices()
		sheet.save()
		if abs(flt(sheet.unit_cost) - before) > 0.0049:
			changes.append({"sheet": name, "boq_ref": sheet.boq_ref, "before": before, "after": sheet.unit_cost})
	return changes
