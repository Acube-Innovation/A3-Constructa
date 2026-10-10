# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""An awarded Sales Order carries the contract - catalogue 4.1.

- Its terms (contract type, retention and its cap, advance and its recovery,
  defects liability) come from the Awarded Quotation; changing them on the
  order needs the Accounts Manager role.
- Every line bills one line of the award's BOQ on one WBS node. A line names
  its BOQ and the line's ref; the WBS is filled in where it is clear (see
  wbs_for). A draft may be incomplete while it is prepared; submitting it is
  refused until every line has its BOQ line and WBS.
- Payment terms and taxes are ERPNext's own fields; an awarded order with none
  takes the contract defaults from A3 Constructa Settings.
"""

import frappe
from frappe import _
from frappe.utils import flt

TERMS = ("contract_type", "retention_percent", "retention_cap_percent", "advance_percent", "advance_recovery_percent",
         "defects_liability_months")
TERMS_ROLE = "Accounts Manager"


def validate(doc, method=None):
	if not doc.get("awarded_quotation"):
		return
	award = frappe.db.get_value("Awarded Quotation", doc.awarded_quotation, ["project", *TERMS], as_dict=True)
	if not award:
		return
	apply_terms(doc, award)
	doc.project = doc.project or award.project
	set_standard_terms(doc)
	# Catalogue 4.2: on an award billed by milestones, the schedule follows them.
	from a3_constructa.api.milestone_billing import apply_to_order

	apply_to_order(doc, frappe.get_doc("Awarded Quotation", doc.awarded_quotation))
	award_boqs = boqs_of(doc.awarded_quotation)
	for row in doc.items:
		resolve_line(doc, row, award_boqs)


def apply_terms(doc, award):
	"""Copy the award's terms; a different value needs the Accounts Manager role."""
	before = doc.get_doc_before_save()
	changed = []
	for field in TERMS:
		value, contract = doc.get(field), award.get(field)
		if value in (None, "", 0) and contract not in (None, ""):
			doc.set(field, contract)
			continue
		was = before.get(field) if before else None
		if not equal(value, contract) and (not before or not equal(value, was)):
			changed.append(field)
	if changed and TERMS_ROLE not in frappe.get_roles():
		labels = ", ".join(_(doc.meta.get_label(f)) for f in changed)
		frappe.throw(_("The contract terms come from award {0}; only an Accounts Manager can change them on the order ({1}).").format(doc.awarded_quotation, labels),
		             title=_("Contract terms"))


def equal(a, b):
	if isinstance(a, (int, float)) or isinstance(b, (int, float)):
		return abs(flt(a) - flt(b)) < 1e-9
	return (a or "") == (b or "")


def set_standard_terms(doc):
	if not doc.payment_terms_template:
		terms = frappe.db.get_single_value("A3 Constructa Settings", "contract_payment_terms")
		if terms:
			doc.payment_terms_template = terms
			doc.set("payment_schedule", [])
	if not doc.taxes_and_charges and not doc.taxes:
		taxes = frappe.db.get_single_value("A3 Constructa Settings", "contract_taxes")
		if taxes and frappe.db.get_value("Sales Taxes and Charges Template", taxes, "company") == doc.company:
			doc.taxes_and_charges = taxes
			# ERPNext only pulls a template's rows into a new document; do it here too.
			doc.append_taxes_from_master("Sales Taxes and Charges Template")
			doc.run_method("calculate_taxes_and_totals")


def boqs_of(award):
	"""The BOQs that price the award: those naming it, and its components' BOQs."""
	boqs = set(frappe.get_all("BOQ", filters={"awarded_quotation": award, "docstatus": ["<", 2]}, pluck="name"))
	boqs |= set(frappe.get_all("Awarded Quotation Component", filters={"parent": award, "parenttype": "Awarded Quotation",
	                                                                    "boq": ["is", "set"]}, pluck="boq"))
	return boqs


def resolve_line(doc, row, award_boqs):
	if not row.get("boq"):
		row.boq_item = None
		return
	if row.boq not in award_boqs:
		frappe.throw(_("Row {0}: BOQ {1} does not price award {2}.").format(row.idx, row.boq, doc.awarded_quotation))
	line = None
	if row.get("boq_ref"):
		line = frappe.db.get_value("BOQ Item", {"parent": row.boq, "parenttype": "BOQ", "boq_ref": row.boq_ref},
		                           ["name", "boq_ref", "cost_head", "wbs", "cost_code"], as_dict=True)
		if not line:
			frappe.throw(_("Row {0}: BOQ {1} has no line {2}.").format(row.idx, row.boq, row.boq_ref))
	elif row.get("boq_item"):
		line = frappe.db.get_value("BOQ Item", {"name": row.boq_item, "parent": row.boq},
		                           ["name", "boq_ref", "cost_head", "wbs", "cost_code"], as_dict=True)
	if not line:
		row.boq_item = None
		return
	row.boq_item, row.boq_ref = line.name, line.boq_ref
	if not row.get("cost_code") and line.cost_code:
		row.cost_code = line.cost_code
	if not row.get("wbs"):
		row.wbs = wbs_for(doc.project, doc.awarded_quotation, line)
	if row.get("wbs") and doc.project and frappe.db.get_value("WBS", row.wbs, "project") != doc.project:
		frappe.throw(_("Row {0}: WBS {1} is not part of project {2}.").format(row.idx, row.wbs, doc.project))


def wbs_for(project, award, line):
	"""The WBS a BOQ line is billed on, where it is clear:
	1. the line's own WBS;
	2. the WBS of the same line (by ref) on the award's budget BOQ, or the one
	   WBS its submitted allocations put it on;
	3. the one Active WBS of the project with the line's cost head;
	4. for a line with no cost head (the contingency), the project's one top node."""
	if line.wbs:
		return line.wbs
	for budget in frappe.get_all("BOQ", filters={"awarded_quotation": award, "boq_stage": ["in", ["Budget", "Contract"]],
	                                             "docstatus": ["<", 2]}, pluck="name"):
		twin = frappe.db.get_value("BOQ Item", {"parent": budget, "boq_ref": line.boq_ref}, ["name", "wbs"], as_dict=True) if line.boq_ref else None
		if twin and twin.wbs:
			return twin.wbs
		if twin:
			placed = set(frappe.get_all("WBS Allocation Item", filters={"boq_item": twin.name, "docstatus": 1}, pluck="parent"))
			nodes = {frappe.db.get_value("WBS Allocation", p, "wbs") for p in placed}
			if len(nodes) == 1:
				return nodes.pop()
	if not project:
		return None
	if line.cost_head:
		nodes = frappe.get_all("WBS", filters={"project": project, "cost_head": line.cost_head, "status": "Active", "is_group": 0}, pluck="name")
		return nodes[0] if len(nodes) == 1 else None
	roots = frappe.get_all("WBS", filters={"project": project, "parent_wbs": ["is", "not set"], "status": "Active"}, pluck="name")
	return roots[0] if len(roots) == 1 else None


def before_submit(doc, method=None):
	if not doc.get("awarded_quotation"):
		return
	missing = [str(row.idx) for row in doc.items if not (row.get("boq") and row.get("boq_item") and row.get("wbs"))]
	if missing:
		rows = (_("row {0}") if len(missing) == 1 else _("rows {0}")).format(", ".join(missing))
		frappe.throw(_("Every line of an awarded order needs its BOQ line and WBS. Complete {0}.").format(rows),
		             title=_("BOQ line and WBS needed"))
	if not doc.payment_terms_template:
		frappe.throw(_("Set the Payment Terms Template: an awarded order is paid on the contract's terms."), title=_("Payment terms needed"))
