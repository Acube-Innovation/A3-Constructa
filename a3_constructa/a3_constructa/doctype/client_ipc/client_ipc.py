# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Client IPC - catalogue 4.3, 4.4, 4.5 and 12.4: the interim payment certificate
we raise on the client, modelled on the subcontractor Work Certificate.

Each line is a line of the contract: a BOQ line the award's order points at, or,
for an award priced by components only, a component. A line carries what earlier
certificates certified, what is claimed this period, and what the client's engineer
certifies; the cumulative may not pass the contract quantity unless an approved
variation order adds quantity on that WBS.

From the certified gross this period (work plus materials on site):
- retention is held at the order's rate until it reaches the cap;
- the advance is recovered at the order's rate until nothing is left to recover;
- net due = gross - retention - advance recovery.

Draft, then Submitted to Client while the client checks it; submitting it means it
is Certified, and "Create Sales Invoice" makes the invoice (status Invoiced). An
opening certificate records work invoiced before certificates were kept here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ClientIPC(Document):
	def validate(self):
		award = frappe.get_doc("Awarded Quotation", self.awarded_quotation)
		if award.status == "Cancelled":
			frappe.throw(_("{0} is cancelled.").format(award.name))
		self.set_header(award)
		self.set_ipc_no()
		self.calculate_lines(award)
		self.calculate_deductions(award)
		if self.docstatus == 0 and self.status not in ("Draft", "Submitted to Client"):
			self.status = "Draft"

	def set_header(self, award):
		self.customer, self.project, self.company = award.customer, award.project, award.company
		self.currency = award.currency
		self.sales_order = self.sales_order or frappe.db.get_value("Sales Order", {"awarded_quotation": award.name, "docstatus": 1}, "name")
		order = frappe.db.get_value("Sales Order", self.sales_order, ["retention_percent", "retention_cap_percent", "advance_recovery_percent"],
		                            as_dict=True) if self.sales_order else None
		# The order's terms; an order from before P-04A carries none, so the award's apply.
		term = lambda field: flt(order.get(field)) if order and flt(order.get(field)) else flt(award.get(field))
		self.retention_percent = term("retention_percent")
		cap_percent = term("retention_cap_percent")
		self.retention_cap = flt(contract_value(award) * cap_percent / 100, 2) if cap_percent else 0
		self.advance_recovery_percent = term("advance_recovery_percent")

	def set_ipc_no(self):
		if self.ipc_no:
			return
		last = frappe.db.sql("""select max(ipc_no) from `tabClient IPC` where awarded_quotation = %s and docstatus < 2 and name != %s""",
		                     (self.awarded_quotation, self.name or ""))[0][0]
		self.ipc_no = (last or 0) + 1

	def calculate_lines(self, award):
		previous = certified_before(self.awarded_quotation, self.name)
		extra = variation_qty(award.name)
		claimed = certified = 0.0
		for row in self.items:
			if self.docstatus == 0 and self.status == "Draft":
				row.certified_qty = row.this_period_qty  # the engineer certifies once the claim is with the client
			row.previous_qty = previous.get(row.line_key, 0)
			row.cumulative_qty = flt(row.previous_qty) + flt(row.certified_qty)
			limit = flt(row.contract_qty) + extra.get((row.wbs, row.uom), 0)
			if flt(row.contract_qty) and flt(row.previous_qty) + max(flt(row.this_period_qty), flt(row.certified_qty)) > limit + 1e-9:
				frappe.throw(_("Row {0}: {1} would reach {2} of {3} {4} contracted. Raise an approved variation order on {5} for the extra.").format(
					row.idx, frappe.bold(row.line_ref or row.description), flt(row.previous_qty) + max(flt(row.this_period_qty), flt(row.certified_qty)),
					flt(row.contract_qty), row.uom or "", row.wbs or _("its WBS")), title=_("More than contracted"))
			row.previous_amount = flt(flt(row.previous_qty) * flt(row.rate), 2)
			row.claimed_amount = flt(flt(row.this_period_qty) * flt(row.rate), 2)
			row.this_period_amount = flt(flt(row.certified_qty) * flt(row.rate), 2)
			row.cumulative_amount = flt(row.previous_amount + row.this_period_amount, 2)
			row.currency = self.currency
			claimed += row.claimed_amount
			certified += row.this_period_amount
		mos = flt(self.materials_on_site)
		self.claimed_amount = flt(claimed + mos, 2)
		self.certified_amount = flt(certified + mos, 2)
		self.gross_this_period = self.certified_amount

	def calculate_deductions(self, award):
		before = deductions_before(self.awarded_quotation, self.name)
		gross = flt(self.gross_this_period)
		if self.opening_invoice:
			retention = recovery = 0.0
		else:
			retention = gross * flt(self.retention_percent) / 100
			if flt(self.retention_cap):
				retention = min(retention, max(flt(self.retention_cap) - before.retention, 0))
			available = max(advance_billed(self.awarded_quotation) - before.recovered, 0)
			recovery = min(gross * flt(self.advance_recovery_percent) / 100, available)
		self.retention_this_period = flt(retention, 2)
		self.retention_cumulative = flt(before.retention + retention, 2)
		self.advance_recovered_this_period = flt(recovery, 2)
		self.advance_recovered_to_date = flt(before.recovered + recovery, 2)
		self.advance_balance = flt(advance_billed(self.awarded_quotation) - self.advance_recovered_to_date, 2)
		self.net_due = flt(gross - self.retention_this_period - self.advance_recovered_this_period, 2)

	def before_submit(self):
		if not self.items and not flt(self.materials_on_site):
			frappe.throw(_("Add the contract lines (Get contract lines) before certifying."))
		if self.opening_invoice:
			self.status, self.sales_invoice = "Invoiced", self.opening_invoice
		else:
			self.status = "Certified"

	def on_cancel(self):
		if self.sales_invoice and not self.opening_invoice and frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus") == 1:
			frappe.throw(_("Cancel invoice {0} first.").format(self.sales_invoice))


def contract_value(award):
	return flt(award.revised_contract_value) or flt(award.contract_value)


def certified_before(award, exclude):
	out = {}
	for r in frappe.db.sql("""select item.line_key, sum(item.certified_qty)
		from `tabClient IPC Item` item join `tabClient IPC` ipc on ipc.name = item.parent
		where ipc.awarded_quotation = %s and ipc.docstatus = 1 and ipc.name != %s group by item.line_key""", (award, exclude or "")):
		out[r[0]] = flt(r[1])
	return out


def deductions_before(award, exclude):
	r = frappe.db.sql("""select sum(retention_this_period), sum(advance_recovered_this_period) from `tabClient IPC`
		where awarded_quotation = %s and docstatus = 1 and name != %s""", (award, exclude or ""))[0]
	return frappe._dict(retention=flt(r[0]), recovered=flt(r[1]))


def advance_billed(award):
	return flt(frappe.db.sql("""select sum(net_total) from `tabSales Invoice`
		where awarded_quotation = %s and docstatus = 1 and is_advance_invoice = 1""", award)[0][0])


def variation_qty(award):
	"""Extra quantity approved variation orders add, per (WBS, UOM)."""
	out = {}
	for r in frappe.db.sql("""select item.wbs, item.uom, sum(item.qty) from `tabVariation Order Item` item
		join `tabVariation Order` vo on vo.name = item.parent
		where vo.awarded_quotation = %s and vo.status = 'Approved' group by item.wbs, item.uom""", award):
		out[(r[0], r[1])] = flt(r[2])
	return out


@frappe.whitelist()
def get_contract_lines(award: str) -> list[dict]:
	"""The contract's lines: the BOQ lines the award's order bills, or else the award's
	components, with what earlier certificates certified."""
	from a3_constructa.overrides.sales_order import wbs_for

	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("read")
	lines = []
	so = frappe.db.get_value("Sales Order", {"awarded_quotation": award, "docstatus": 1}, "name")
	if so:
		seen = set()
		for r in frappe.get_all("Sales Order Item", filters={"parent": so, "boq_item": ["is", "set"]},
		                        fields=["boq", "boq_item", "wbs", "cost_code"], order_by="idx"):
			if r.boq_item in seen:
				continue
			seen.add(r.boq_item)
			b = frappe.db.get_value("BOQ Item", r.boq_item, ["boq_ref", "description", "item_name", "uom", "boq_qty", "is_allowance",
			                                                 "amount", "selling_rate", "approved_rate", "rate"], as_dict=True)
			if not b:
				continue
			allowance = bool(b.is_allowance)
			lines.append({"line_key": r.boq_item, "boq": r.boq, "boq_item": r.boq_item, "line_ref": b.boq_ref,
			              "description": b.description or b.item_name, "uom": "Lump Sum" if allowance else b.uom,
			              "contract_qty": 1 if allowance else flt(b.boq_qty),
			              "rate": flt(b.selling_rate) or flt(b.approved_rate) or flt(b.rate) or (flt(b.amount) if allowance else 0),
			              "wbs": r.wbs, "cost_code": r.cost_code})
	if not lines:
		for c in a.components:
			lines.append({"line_key": f"component:{c.name}", "boq": c.boq, "line_ref": (c.component or "").split(" ")[0][:12],
			              "description": c.component, "uom": c.uom or "Lump Sum", "contract_qty": flt(c.qty) or 1, "rate": flt(c.rate),
			              "wbs": wbs_for(a.project, a.name, frappe._dict(wbs=None, boq_ref=None, cost_head=c.cost_head)) if a.project else None})
	previous = certified_before(award, None)
	for line in lines:
		line["previous_qty"] = previous.get(line["line_key"], 0)
	return lines


@frappe.whitelist()
def make_sales_invoice(ipc: str) -> str:
	from a3_constructa.api.client_billing import invoice_for_ipc

	return invoice_for_ipc(ipc)
