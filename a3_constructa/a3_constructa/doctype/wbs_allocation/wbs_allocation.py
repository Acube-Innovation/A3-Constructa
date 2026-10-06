# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, fmt_money


class WBSAllocation(Document):
	"""Splits approved BOQ lines across WBS nodes (catalogue 1.4, 1.5).

	The 100% rule: across every draft and submitted allocation, a BOQ line can
	be allocated up to its approved qty and no more; an allowance line up to
	what is left of the allowance. Submitting locks an allocation; a change is a
	cancel and amend, and a cancelled allocation releases what it held.
	"""

	def validate(self):
		self.set_line_details()
		self.calculate_amounts()
		self.apply_100_percent_rule()

	def before_submit(self):
		if self.boq and frappe.db.get_value("BOQ", self.boq, "docstatus") != 1:
			frappe.throw(_("BOQ {0} is not approved yet. Allocate it once it is approved.").format(self.boq))

	def set_line_details(self):
		lines = get_boq_lines([row.boq_item for row in self.items if row.boq_item])
		for row in self.items:
			if not row.boq_item:
				row.is_allowance = 0
				if not row.item_code:
					frappe.throw(_("Row {0}: pick the item, or fetch the line from the BOQ.").format(row.idx))
				continue
			line = lines.get(row.boq_item)
			if not line or (self.boq and line.parent != self.boq):
				frappe.throw(_("Row {0}: the BOQ line it points to is not part of BOQ {1}. Fetch the lines again.").format(row.idx, self.boq))
			row.is_allowance = line.is_allowance
			row.description = line.description if line.is_allowance else line.item_name
			row.item_code = None if line.is_allowance else (row.item_code or line.item_code)
			row.cost_code = row.cost_code or line.cost_code

	def calculate_amounts(self):
		for row in self.items:
			if row.is_allowance:
				row.allocated_qty = row.rate = 0
			else:
				row.allocated_amount = flt(row.allocated_qty) * flt(row.rate)
		self.total_allocated = sum(flt(row.allocated_amount) for row in self.items)

	def apply_100_percent_rule(self):
		"""Refuse any line allocated past what was approved, and set the balances."""
		keys = list({row.boq_item for row in self.items if row.boq_item})
		lines = get_boq_lines(keys)
		elsewhere = allocated_elsewhere(keys, self.name)
		here = {}
		for row in self.items:
			if row.boq_item:
				measure = "allocated_amount" if row.is_allowance else "allocated_qty"
				here[row.boq_item] = here.get(row.boq_item, 0) + flt(row.get(measure))

		for row in self.items:
			if not row.boq_item:
				row.balance_qty = row.balance_amount = 0
				continue
			line = lines[row.boq_item]
			other = elsewhere.get(row.boq_item, {})
			if row.is_allowance:
				limit, taken = flt(line.budget_amount), flt(other.get("amount"))
				left = limit - taken - here[row.boq_item]
				row.balance_qty, row.balance_amount = 0, left
				if left < -0.005:
					self.refuse(row, line, limit, taken, other, money=True)
			else:
				limit, taken = flt(line.approved_qty), flt(other.get("qty"))
				left = limit - taken - here[row.boq_item]
				row.balance_qty, row.balance_amount = left, 0
				if left < -0.0005:
					self.refuse(row, line, limit, taken, other, money=False)

	def refuse(self, row, line, limit, taken, other, money):
		currency = frappe.db.get_value("BOQ", line.parent, "currency")
		show = (lambda v: fmt_money(v, currency=currency)) if money else (lambda v: f"{flt(v):,g} {line.uom or ''}".strip())
		what = line.description if line.is_allowance else line.item_code
		where = ", ".join(f"{name}: {show(v)}" for name, v in other.get("by_doc", [])) or _("nothing yet")
		frappe.throw(
			_("Row {0}: BOQ line {1} ({2}) of {3} has {4} approved. Already allocated: {5} ({6}). Left to allocate: {7}.").format(
				row.idx, line.idx, frappe.bold(what), line.parent, frappe.bold(show(limit)),
				show(taken), where, frappe.bold(show(max(limit - taken, 0))),
			),
			title=_("More than 100% of the BOQ line"),
		)


def get_boq_lines(names):
	if not names:
		return {}
	rows = frappe.get_all(
		"BOQ Item",
		filters={"name": ["in", names], "parenttype": "BOQ"},
		fields=["name", "parent", "idx", "item_code", "item_name", "description", "uom", "cost_code",
		        "is_allowance", "approved_qty", "approved_rate", "budget_amount"],
	)
	return {r.name: r for r in rows}


def allocated_elsewhere(boq_items, this):
	"""Per BOQ line: qty and amount held by other draft and submitted allocations."""
	if not boq_items:
		return {}
	rows = frappe.db.sql(
		"""
		select item.boq_item, alloc.name, sum(item.allocated_qty) as qty, sum(item.allocated_amount) as amount
		from `tabWBS Allocation Item` item
		inner join `tabWBS Allocation` alloc on alloc.name = item.parent
		where item.boq_item in %(lines)s and alloc.name != %(this)s and alloc.docstatus < 2
		group by item.boq_item, alloc.name
		order by alloc.name
		""",
		{"lines": boq_items, "this": this or ""},
		as_dict=True,
	)
	out = {}
	for r in rows:
		entry = out.setdefault(r.boq_item, {"qty": 0, "amount": 0, "by_doc": [], "by_doc_amount": []})
		entry["qty"] += flt(r.qty)
		entry["amount"] += flt(r.amount)
		entry["by_doc"].append((r.name, flt(r.qty)))
		entry["by_doc_amount"].append((r.name, flt(r.amount)))
	for entry in out.values():
		# An allowance is held by amount, so name the documents by amount too.
		if not any(q for _n, q in entry["by_doc"]):
			entry["by_doc"] = entry["by_doc_amount"]
	return out


@frappe.whitelist()
def get_lines_to_allocate(boq, allocation=None):
	"""The BOQ's lines with what is still free to allocate, for Get Lines from BOQ."""
	frappe.has_permission("BOQ", "read", boq, throw=True)
	lines = frappe.get_all(
		"BOQ Item",
		filters={"parent": boq, "parenttype": "BOQ"},
		fields=["name", "idx", "item_code", "item_name", "description", "uom", "cost_code", "is_allowance",
		        "approved_qty", "approved_rate", "budget_amount"],
		order_by="idx",
	)
	held = allocated_elsewhere([l.name for l in lines], allocation)
	out = []
	for l in lines:
		other = held.get(l.name, {})
		if l.is_allowance:
			free = flt(l.budget_amount) - flt(other.get("amount"))
		else:
			free = flt(l.approved_qty) - flt(other.get("qty"))
		if free > 0.0005:
			out.append({**l, "free": free})
	return out
