# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Quotation from a tender BOQ - catalogue 2.7.

A priced Tender BOQ becomes a Quotation: one line per BOQ line at its selling
rate, preliminaries first and as lines of their own, the contingency last. Each
line keeps its BOQ ref, cost head and cost rate, so the quotation knows its own
margin: (net total - cost - contingency) / net total, the contingency being
neither cost nor margin, as on the BOQ.

Re-pricing is cancel and amend (number -1, -2): each revision must give a
reason, and the Revision History table logs every issue's value and its change
on the one before. Below the minimum margin in A3 Constructa Settings the
"Quotation Margin Approval" workflow routes the quotation to Pending Management
Approval; check_margin_approval refuses a submit that skipped it.
"""

import json

import frappe
from frappe import _
from frappe.model.workflow import get_workflow_name
from frappe.utils import add_days, flt, today

from a3_constructa.a3_constructa.doctype.boq.boq import preliminaries_heads

APPROVER_ROLE = "A3 Constructa Admin"


def validate(doc, method=None):
	if doc.is_new() and not doc.amended_from and doc.get("opportunity"):
		from a3_constructa.overrides.opportunity import refuse_if_no_go

		refuse_if_no_go(doc.opportunity)
	set_revision(doc)
	set_margin(doc)
	log_revision(doc)


def set_revision(doc):
	if not doc.amended_from:
		doc.revision_no = doc.revision_no or 0
		return
	doc.revision_no = (frappe.db.get_value("Quotation", doc.amended_from, "revision_no") or 0) + 1
	if not (doc.revision_reason or "").strip():
		frappe.throw(_("Say why the quotation is being revised (Revision Reason)."), title=_("Revision reason needed"))


def set_margin(doc):
	if not doc.boq:
		doc.margin_percent, doc.below_minimum_margin = None, 0
		return
	cost = sum(flt(row.cost_rate) * flt(row.qty) for row in doc.items if not row.is_contingency)
	contingency = sum(flt(row.amount) for row in doc.items if row.is_contingency)
	net = flt(doc.net_total)
	doc.margin_percent = (net - cost - contingency) / net * 100 if net else 0
	doc.below_minimum_margin = int(flt(doc.margin_percent, 2) < minimum_margin())


DEFAULT_MIN_MARGIN = 10.0


def minimum_margin():
	"""The setting, or 10% while it has never been saved (0 is a real choice: no minimum)."""
	value = frappe.db.get_value("Singles", {"doctype": "A3 Constructa Settings", "field": "min_margin_percent"}, "value", order_by=None)
	return flt(value) if value is not None else DEFAULT_MIN_MARGIN


def log_revision(doc):
	"""Keep one Revision History row per issue; earlier rows come across on amend."""
	row = next((r for r in doc.revisions if r.revision == doc.revision_no), None) or doc.append("revisions", {"revision": doc.revision_no})
	previous = frappe.db.get_value("Quotation", doc.amended_from, "grand_total") if doc.amended_from else None
	row.update({
		"quotation": doc.name,
		"revision_date": doc.transaction_date,
		"reason": (doc.revision_reason or "").strip() or _("First issue"),
		"value": doc.grand_total,
		"change": flt(doc.grand_total) - flt(previous) if previous is not None else None,
		"margin_percent": doc.margin_percent,
		"currency": doc.currency,
	})


def set_cancelled_state(doc, method=None):
	"""Frappe leaves the workflow state alone on cancel; show the quotation as Cancelled."""
	if doc.get("workflow_state") and get_workflow_name("Quotation"):
		doc.db_set("workflow_state", "Cancelled", update_modified=False)


def check_margin_approval(doc, method=None):
	"""A quotation below the minimum margin is submitted only through management approval."""
	if not doc.below_minimum_margin:
		return
	if get_workflow_name("Quotation"):
		if doc.get("workflow_state") == "Approved":
			return
	elif APPROVER_ROLE in frappe.get_roles():
		return
	frappe.throw(
		_("The margin is {0}%, below the {1}% minimum. Use Submit for Approval: management approves it before it goes to the client.").format(
			f"{flt(doc.margin_percent, 2):g}", f"{flt(minimum_margin(), 2):g}"),
		title=_("Management approval needed"),
	)


# ---------------------------------------------------------------- from the BOQ

def boq_lines(boq):
	"""Quotation lines for a priced tender BOQ, preliminaries first, contingency last.

	A line that draws from an allowance is inside that allowance's sum, so it is
	not quoted again.
	"""
	prelim = preliminaries_heads()
	rows = [r for r in boq.items if not r.draws_from_allowance]
	rows.sort(key=lambda r: (2 if r.is_contingency else 0 if (r.is_allowance and r.cost_head in prelim) else 1, r.idx))
	lines = []
	for r in rows:
		description = r.description or r.item_name or r.item_code or r.boq_ref
		lump = bool(r.is_allowance)
		line = {
			"item_name": (r.item_name or description or "")[:140],
			"description": description,
			"qty": 1 if lump else flt(r.boq_qty),
			"uom": (r.uom or "Lump Sum") if not lump else "Lump Sum",
			"conversion_factor": 1,
			"rate": flt(r.selling_rate),
			"price_list_rate": flt(r.selling_rate),
			"boq_item": r.name,
			"boq_ref": r.boq_ref,
			"cost_head": r.cost_head,
			"cost_rate": 0 if r.is_contingency else flt(r.amount) if lump else flt(r.cost_rate),
			"is_contingency": r.is_contingency,
		}
		# The client buys work, not the materials an estimate is built from: a line
		# carries its item only when that item is sold, in the unit measured.
		item = frappe.get_cached_value("Item", r.item_code, ["is_sales_item", "stock_uom"], as_dict=True) if r.item_code and not lump else None
		if item and item.is_sales_item and item.stock_uom == line["uom"]:
			line.update({"item_code": r.item_code, "stock_uom": item.stock_uom})
		lines.append(line)
	return lines


def check_priced(boq):
	if boq.boq_stage != "Tender":
		frappe.throw(_("Only a Tender BOQ is quoted from; {0} is a {1} BOQ.").format(boq.name, _(boq.boq_stage)))
	if boq.docstatus != 0:
		frappe.throw(_("{0} is not a draft.").format(boq.name))
	if boq.unpriced_lines:
		frappe.throw(_("{0} lines of {1} have no cost rate yet. Price them on their estimate sheets first.").format(
			boq.unpriced_lines, boq.name), title=_("Not fully priced"))
	if not flt(boq.selling_total):
		frappe.throw(_("{0} has no selling total yet.").format(boq.name))


def party_for(boq):
	if boq.customer:
		return "Customer", boq.customer
	if boq.opportunity:
		opp = frappe.db.get_value("Opportunity", boq.opportunity, ["opportunity_from", "party_name"], as_dict=True)
		if opp and opp.opportunity_from in ("Customer", "Lead", "Prospect") and opp.party_name:
			return opp.opportunity_from, opp.party_name
	frappe.throw(_("Set the client on {0} (Customer, or an Opportunity) before quoting it.").format(boq.name))


def set_lines(quotation, boq):
	lines = boq_lines(boq)
	quotation.set("items", [])
	for line in lines:
		quotation.append("items", line)
	quotation.run_method("set_missing_values")
	# set_missing_values may bring in a price list rate for an item line; the BOQ's selling rate stands.
	selling = {line["boq_item"]: line["rate"] for line in lines}
	for row in quotation.items:
		if row.boq_item in selling:
			row.rate = row.price_list_rate = selling[row.boq_item]
			row.discount_percentage = row.discount_amount = row.margin_rate_or_amount = 0
	quotation.run_method("calculate_taxes_and_totals")


@frappe.whitelist()
def make_from_boq(boq: str) -> dict:
	"""Create Quotation on a priced Tender BOQ; return the open one if it already has it."""
	frappe.has_permission("Quotation", "create", throw=True)
	frappe.has_permission("BOQ", "read", doc=boq, throw=True)
	existing = frappe.db.get_value("Quotation", {"boq": boq, "docstatus": ["<", 2]}, "name", order_by="creation desc")
	if existing:
		return {"name": existing, "existing": True}
	doc = frappe.get_doc("BOQ", boq)
	check_priced(doc)
	quotation_to, party = party_for(doc)
	company = (frappe.db.get_value("Opportunity", doc.opportunity, "company") if doc.opportunity else None) \
		or frappe.defaults.get_user_default("Company")
	q = frappe.new_doc("Quotation")
	q.update({
		"quotation_to": quotation_to, "party_name": party, "company": company, "currency": doc.currency,
		"transaction_date": today(), "valid_till": add_days(today(), 30), "order_type": "Sales",
		"opportunity": doc.opportunity, "boq": doc.name, "ignore_pricing_rule": 1,
	})
	set_lines(q, doc)
	q.insert()
	return {"name": q.name, "existing": False}


@frappe.whitelist()
def update_from_boq(quotation: str) -> dict:
	"""Take the BOQ's current selling rates into a draft quotation (after re-pricing the BOQ)."""
	q = frappe.get_doc("Quotation", quotation)
	q.check_permission("write")
	if q.docstatus != 0 or not q.boq:
		frappe.throw(_("Only a draft quotation made from a BOQ can be updated from it."))
	frappe.has_permission("BOQ", "read", doc=q.boq, throw=True)
	before = flt(q.grand_total)
	boq = frappe.get_doc("BOQ", q.boq)
	check_priced(boq)
	set_lines(q, boq)
	q.save()
	return {"before": before, "after": q.grand_total, "margin_percent": q.margin_percent}


@frappe.whitelist()
def declare_lost(quotation: str, lost_reasons: str | list, competitors: str | list | None = None,
                 detailed_reason: str | None = None, competitor_price: float | None = None):
	"""ERPNext's Set as Lost, plus the price the job went for."""
	q = frappe.get_doc("Quotation", quotation)
	lost_reasons = json.loads(lost_reasons) if isinstance(lost_reasons, str) else lost_reasons
	competitors = json.loads(competitors) if isinstance(competitors, str) else (competitors or [])
	if flt(competitor_price) < 0:
		frappe.throw(_("Competitor price cannot be negative."))
	q.competitor_price = flt(competitor_price) or None
	q.declare_enquiry_lost(lost_reasons, competitors, detailed_reason)
