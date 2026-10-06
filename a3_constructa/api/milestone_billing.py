# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Milestone billing - catalogue 4.2.

On an award billed by milestones (billing basis "Milestones"), completing a
milestone (its actual end) makes its billing % due. "Bill due milestones" turns
each due milestone into a draft Sales Invoice for billing % × the revised
contract value, on the WBS of the milestone's component, and links it back.
Cancelling or deleting that invoice makes the milestone due again.

The award's Sales Order takes its payment schedule from the milestones: one
row per milestone with a billing %, due its planned end plus the contract's
credit days. An award billed by progress claims keeps its milestones as the
programme only; the interim certificates of P-04C bill it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from a3_constructa.api.award_handover import contract_item
from a3_constructa.overrides.sales_order import wbs_for

BASIS = "Milestones"


def bills_by_milestones(award) -> bool:
	return (award.get("billing_basis") or BASIS) == BASIS


def is_due(award, row) -> bool:
	return bool(bills_by_milestones(award) and row.actual_end and flt(row.billing_percent) > 0 and not row.sales_invoice)


def milestone_amount(award, row) -> float:
	value = flt(award.revised_contract_value) or flt(award.contract_value)
	return flt(value * flt(row.billing_percent) / 100, 2)


def component_wbs(award, row):
	"""The milestone's WBS: from its component's cost head, else the project's top node."""
	if not award.project:
		return None
	head = None
	if row.component:
		head = next((c.cost_head for c in award.components if c.component == row.component), None)
	return wbs_for(award.project, award.name, frappe._dict(wbs=None, boq_ref=None, cost_head=head))


@frappe.whitelist()
def bill_due_milestones(award: str) -> list[str]:
	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("read")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	if not bills_by_milestones(a):
		frappe.throw(_("{0} is billed by progress claims, not milestones.").format(a.name))
	due = [row for row in a.milestones if is_due(a, row)]
	if not due:
		frappe.throw(_("No milestone of {0} is due for billing: a milestone falls due when its actual end is entered.").format(a.name),
		             title=_("Nothing to bill"))
	made = []
	for row in due:
		si = make_invoice(a, row)
		frappe.db.set_value("Awarded Quotation Milestone", row.name, {"sales_invoice": si.name, "billing_due": 0}, update_modified=False)
		made.append(si.name)
	a.add_comment("Info", _("Billed milestones: {0}").format(", ".join(made)))
	return made


def make_invoice(a, row):
	settings = frappe.get_cached_doc("A3 Constructa Settings")
	amount = milestone_amount(a, row)
	head = next((c.cost_head for c in a.components if c.component == row.component), None) if row.component else None
	si = frappe.new_doc("Sales Invoice")
	si.update({
		"customer": a.customer, "company": a.company, "currency": a.currency, "project": a.project,
		"awarded_quotation": a.name, "posting_date": today(), "set_posting_time": 0,
		"payment_terms_template": settings.contract_payment_terms,
		"remarks": _("Milestone billing: {0}, {1}% of the revised contract value of {2}.").format(
			row.milestone, flt(row.billing_percent), a.name),
	})
	si.append("items", {
		"item_code": contract_item(head), "qty": 1, "rate": amount, "price_list_rate": amount,
		"description": _("{0} ({1}% of {2})").format(row.milestone, flt(row.billing_percent),
		                                              frappe.format(flt(a.revised_contract_value) or flt(a.contract_value),
		                                                            {"fieldtype": "Currency", "options": "currency"}, doc=a)),
		"wbs": component_wbs(a, row),
	})
	si.run_method("set_missing_values")
	for item in si.items:
		item.rate = item.price_list_rate = amount
		item.discount_percentage = item.discount_amount = 0
	if settings.contract_taxes and frappe.db.get_value("Sales Taxes and Charges Template", settings.contract_taxes, "company") == a.company:
		si.taxes_and_charges = settings.contract_taxes
		si.set("taxes", [])
		si.append_taxes_from_master("Sales Taxes and Charges Template")
	si.run_method("calculate_taxes_and_totals")
	si.insert()
	return si


def release_milestone(doc, method=None):
	"""Sales Invoice cancelled or deleted: its milestone is due for billing again."""
	for name in frappe.get_all("Awarded Quotation Milestone", filters={"sales_invoice": doc.name}, pluck="name"):
		frappe.db.set_value("Awarded Quotation Milestone", name, {"sales_invoice": None, "billing_due": 1}, update_modified=False)


# ---------------------------------------------------------------- payment schedule

def schedule_rows(award, terms_template=None):
	"""Payment schedule rows from the milestones: (due date, portion, description)."""
	if not bills_by_milestones(award):
		return []
	rows = [m for m in award.milestones if flt(m.billing_percent) > 0 and m.planned_end]
	if not rows or abs(sum(flt(m.billing_percent) for m in rows) - 100) > 0.001:
		return []
	credit = credit_days(terms_template)
	return [{"due_date": add_days(m.planned_end, credit), "invoice_portion": flt(m.billing_percent),
	         "description": m.milestone[:140]} for m in sorted(rows, key=lambda m: getdate(m.planned_end))]


def credit_days(template):
	if not template:
		return 0
	terms = frappe.get_all("Payment Terms Template Detail", filters={"parent": template}, fields=["credit_days"], limit=1)
	return int(terms[0].credit_days or 0) if terms else 0


def apply_to_order(so, award):
	"""A draft awarded order's payment schedule follows the milestones."""
	rows = schedule_rows(award, so.payment_terms_template)
	if not rows:
		return
	so.set("payment_schedule", [])
	for r in rows:
		so.append("payment_schedule", r)
	so.run_method("set_payment_schedule")


@frappe.whitelist()
def sync_submitted_orders(award: str):
	"""After the programme changes, rewrite the payment schedule of the award's
	submitted orders (nothing is paid against an order's schedule)."""
	a = frappe.get_doc("Awarded Quotation", award) if isinstance(award, str) else award
	for name in frappe.get_all("Sales Order", filters={"awarded_quotation": a.name, "docstatus": 1}, pluck="name"):
		so = frappe.get_doc("Sales Order", name)
		rows = schedule_rows(a, so.payment_terms_template)
		if not rows:
			continue
		total = flt(so.rounded_total) if not so.disable_rounded_total and flt(so.rounded_total) else flt(so.grand_total)
		base = flt(so.base_rounded_total) if not so.disable_rounded_total and flt(so.base_rounded_total) else flt(so.base_grand_total)
		frappe.db.delete("Payment Schedule", {"parent": name, "parenttype": "Sales Order"})
		running = base_running = 0.0
		for i, r in enumerate(rows, 1):
			amount = flt(total * r["invoice_portion"] / 100, 2) if i < len(rows) else flt(total - running, 2)
			base_amount = flt(base * r["invoice_portion"] / 100, 2) if i < len(rows) else flt(base - base_running, 2)
			running += amount
			base_running += base_amount
			child = frappe.get_doc({"doctype": "Payment Schedule", "parent": name, "parenttype": "Sales Order", "parentfield": "payment_schedule",
			                        "idx": i, "docstatus": 1, "due_date": r["due_date"], "invoice_portion": r["invoice_portion"],
			                        "description": r["description"], "payment_amount": amount, "base_payment_amount": base_amount,
			                        "outstanding": amount})
			child.db_insert()
