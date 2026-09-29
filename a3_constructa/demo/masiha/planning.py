# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Steps 2 to 4: the award, its BOQs, the WBS split, and items mapped to budget lines.

Contract value and internal cost budget stay apart, as the client asks. The
Awarded Quotation carries what the client pays (client BOQ rates); each BOQ
carries what the work may cost us (internal budget rates). Both are there on
the porcelain lines: $46.00/m2 sold, $29.12/m2 budgeted.
"""

import frappe
from frappe.utils import flt

from a3_constructa.demo.masiha.common import (
	AWARD_TITLE,
	COMPANY,
	CUSTOMER,
	SELLING_PRICE_LIST,
	at,
	comment,
	day,
	exists,
	insert,
	log,
	project,
	transition,
	user,
	wh,
)

# Internal cost BOQs, one per package: (item, wbs, cost code, qty, estimate rate, approved qty, approved rate)
FLOORING_REV0 = [
	("FIN-POR-600", "MSS-W-FL", "MSS-CC-FIN-M", 1000, 20.00, 1000, 20.00),
	("FIN-ADH-C2", "MSS-W-FL", "MSS-CC-FIN-M", 260, 10.50, 260, 10.50),
	("SVC-TILE-INST", "MSS-W-FL", "MSS-CC-FIN-S", 1000, 8.00, 1000, 8.00),
]
# Revision 1, after design development: the tile budget follows the supplier
# market down, and the grout the first estimate missed is added.
FLOORING_REV1 = [
	("FIN-POR-600", "MSS-W-FL", "MSS-CC-FIN-M", 1000, 20.00, 1000, 18.50),
	("FIN-ADH-C2", "MSS-W-FL", "MSS-CC-FIN-M", 260, 10.50, 260, 9.80),
	("FIN-GRT-CG2", "MSS-W-FL", "MSS-CC-FIN-M", 90, 6.40, 90, 6.40),
	("SVC-TILE-INST", "MSS-W-FL", "MSS-CC-FIN-S", 1000, 8.00, 1000, 7.50),
]
OTHER_BOQS = {
	"MSS-ES": [("CEM-425-50", "MSS-W-ES", "MSS-CC-STR-M", 4200, 11.50, 4200, 11.20),
	           ("STL-Y16", "MSS-W-ES", "MSS-CC-STR-M", 85, 1000.00, 85, 980.00)],
	"MSS-AR-DW": [("DW-ALW-1215", "MSS-W-DW", "MSS-CC-DW-M", 64, 420.00, 64, 410.00),
	              ("DW-DOR-FD90", "MSS-W-DW", "MSS-CC-DW-M", 18, 700.00, 18, 680.00)],
	"MSS-AR-PT": [("PNT-EMU-20", "MSS-W-PT", "MSS-CC-PNT-M", 180, 66.00, 180, 64.00)],
	"MSS-MEP": [("ELE-CBL-4", "MSS-W-MEP", "MSS-CC-MEP-M", 12000, 1.40, 12000, 1.35)],
}

# The WBS split of the client's diagram: one item code, two allocations.
ALLOCATIONS = {
	"MSS-W-FL-A": {"FIN-POR-600": 600, "FIN-ADH-C2": 156, "FIN-GRT-CG2": 54, "SVC-TILE-INST": 600},
	"MSS-W-FL-B": {"FIN-POR-600": 400, "FIN-ADH-C2": 104, "FIN-GRT-CG2": 36, "SVC-TILE-INST": 400},
}


def run():
	boqs = create_boqs()
	award = create_award(boqs)
	create_client_order(award)
	create_allocations(boqs["MSS-AR-FL"])
	create_procurement_plan(boqs["MSS-AR-FL"])
	create_deliverables(award)
	create_variations(award)
	frappe.db.commit()


# ------------------------------------------------------------------- BOQs
def _boq(head, lines, when, revision=0, amended_from=None):
	return insert({
		"doctype": "BOQ", "project": project(), "cost_head": head, "boq_date": day(when),
		"revision_no": revision, "currency": "USD", "amended_from": amended_from,
		"items": [{"item_code": i, "wbs": w, "cost_code": c, "boq_qty": q, "rate": r,
		           "approved_qty": aq, "approved_rate": ar} for i, w, c, q, r, aq, ar in lines],
	})


def _approve(boq, when, note):
	transition("BOQ", boq.name, "Submit for Approval", "qs", at(when, 9))
	return transition("BOQ", boq.name, "Approve", "pm", at(when, 16), note)


def create_boqs() -> dict:
	found = {row.cost_head: row.name for row in frappe.get_all(
		"BOQ", filters={"project": project(), "docstatus": 1}, fields=["name", "cost_head"])}
	if "MSS-AR-FL" in found:
		log("BOQs already present")
		return found

	boqs = {}
	for head, lines in OTHER_BOQS.items():
		boq = _approve(_boq(head, lines, -138), -137, "Budget approved against the internal cost estimate.")
		boqs[head] = boq.name

	# Flooring: approved, then revised. Revision 0 stays on record, cancelled.
	rev0 = _approve(_boq("MSS-AR-FL", FLOORING_REV0, -138), -137, "Initial flooring allowance approved.")
	with_note = "Revised after design development: tile budget to $18.50/m2, adhesive to $9.80, grout added."
	comment("BOQ", rev0.name, with_note, "qs", at(-121, 11))
	rev0 = frappe.get_doc("BOQ", rev0.name)
	rev0.flags.ignore_permissions = True
	rev0.cancel()
	rev1 = _approve(_boq("MSS-AR-FL", FLOORING_REV1, -121, revision=1, amended_from=rev0.name), -120,
	                "Revision 1 approved. Flooring budget $29,124 for 1,000 m2 ($29.12/m2).")
	boqs["MSS-AR-FL"] = rev1.name
	log(f"BOQs approved: {', '.join(boqs.values())}; flooring revised {rev0.name} -> {rev1.name}")
	return boqs


# ------------------------------------------------------------------ award
def create_award(boqs) -> str:
	existing = exists("Awarded Quotation", {"title": AWARD_TITLE, "company": COMPANY})
	if existing:
		log(f"award already present: {existing}")
		return existing

	fl = boqs["MSS-AR-FL"]
	# The client's BOQ, at selling rates.
	components = [
		("A1 Earthworks and substructure", "MSS-ES", boqs["MSS-ES"], 1, "Lump Sum", 385000),
		("A2 Reinforced concrete frame", "MSS-ES", boqs["MSS-ES"], 1, "Lump Sum", 612000),
		("B1 Doors and windows", "MSS-AR-DW", boqs["MSS-AR-DW"], 1, "Lump Sum", 48500),
		("B2 Porcelain floor tiling 600x600, ground floor", "MSS-AR-FL", fl, 600, "Square Meter", 46.00),
		("B3 Porcelain floor tiling 600x600, first floor", "MSS-AR-FL", fl, 400, "Square Meter", 46.00),
		("B4 Internal painting, emulsion 2 coats", "MSS-AR-PT", boqs["MSS-AR-PT"], 3200, "Square Meter", 8.50),
		("C1 MEP installations", "MSS-MEP", boqs["MSS-MEP"], 1, "Lump Sum", 26500),
	]
	milestones = [
		("Mobilisation and site set-up", -140, -128, -126, 5, 10),
		("Earthworks and substructure", -125, -70, -62, 25, 20),
		("Reinforced concrete frame", -70, -5, None, 30, 25),
		("Architectural finishes (floors, doors, painting)", -20, 120, None, 25, 25),
		("MEP, testing and handover", 60, 220, None, 15, 20),
	]
	doc = insert({
		"doctype": "Awarded Quotation", "title": AWARD_TITLE, "customer": CUSTOMER, "project": project(),
		"company": COMPANY, "currency": "USD", "award_date": day(-150), "award_reference": "LOA/GPE/INFRA/2026/031",
		"status": "In Progress", "start_date": day(-140), "end_date": day(220), "retention_percent": 5,
		"advance_percent": 10, "defects_liability_months": 12,
		"components": [{"component": c, "cost_head": h, "boq": b, "qty": q, "uom": u, "rate": r,
		                "description": c} for c, h, b, q, u, r in components],
		"milestones": [{"milestone": m, "planned_start": day(s), "planned_end": day(e),
		                "actual_end": day(a) if a is not None else None, "weightage": w, "billing_percent": bill,
		                "status": "In Progress" if a is None and s < 0 else ("Completed" if a is not None else "Not Started")}
		               for m, s, e, a, w, bill in milestones],
		"scope": "<p>Design and build of the Mbandaka Administrative Centre: a two-storey office block with "
		         "porcelain-tiled floors throughout. Contract value and internal cost budget are held separately: "
		         "this award carries the client's rates; the BOQs carry the internal budget.</p>",
	})
	frappe.db.set_value("Awarded Quotation", doc.name, "owner", user("pm"), update_modified=False)
	log(f"award {doc.name}: contract value {flt(doc.contract_value):,.0f} USD, "
	    f"{len(doc.components)} client BOQ lines, {len(doc.milestones)} milestones")
	return doc.name


def create_client_order(award):
	if exists("Sales Order", {"awarded_quotation": award, "docstatus": 1}):
		return
	value = {"CW-STRUCT": 997000, "CW-ARCH": 48500 + 27600 + 18400 + 27200, "CW-MEP": 26500}
	so = insert({
		"doctype": "Sales Order", "customer": CUSTOMER, "company": COMPANY, "transaction_date": day(-148),
		"delivery_date": day(220), "currency": "USD", "selling_price_list": SELLING_PRICE_LIST,
		"project": project(), "awarded_quotation": award, "po_no": "LOA/GPE/INFRA/2026/031", "po_date": day(-150),
		# Each package is 100 units, one per percent of its value, so a progress
		# claim bills the percentage completed.
		"items": [{"item_code": code, "qty": 100, "rate": rate / 100, "delivery_date": day(220),
		           "warehouse": wh("Stores")} for code, rate in value.items()],
	}, submit=True)
	log(f"client order {so.name}: {flt(so.grand_total):,.0f} USD")


# ------------------------------------------------------ WBS allocation (diagram)
def create_allocations(boq):
	if exists("WBS Allocation", {"boq": boq}):
		log("WBS allocations already present")
		return
	lines = {row.item_code: row for row in frappe.get_doc("BOQ", boq).items}
	for wbs, quantities in ALLOCATIONS.items():
		insert({
			"doctype": "WBS Allocation", "project": project(), "boq": boq, "wbs": wbs, "cost_head": "MSS-AR-FL",
			"items": [{"boq_item": lines[item].name, "item_code": item, "cost_code": lines[item].cost_code,
			           "allocated_qty": qty, "rate": lines[item].approved_rate} for item, qty in quantities.items()],
		})
	log("WBS allocations: porcelain 600 m2 to WBS A, 400 m2 to WBS B (same item, cost code and rate)")


def create_procurement_plan(boq):
	if exists("Procurement Plan", {"project": project()}):
		return
	insert({
		"doctype": "Procurement Plan", "project": project(), "cost_head": "MSS-AR-FL", "plan_date": day(-118),
		"status": "Submitted",
		"items": [{"item_code": i, "wbs": w, "cost_code": c, "boq_qty": q, "anticipated_qty": q, "uom": u,
		           "required_on_site_date": day(r), "lead_time_days": lt, "remarks": note}
		          for i, w, c, q, u, r, lt, note in (
		              ("FIN-POR-600", "MSS-W-FL-A", "MSS-CC-FIN-M", 600, "Square Meter", 5, 90, "Import, Spain"),
		              ("FIN-POR-600", "MSS-W-FL-B", "MSS-CC-FIN-M", 400, "Square Meter", 30, 90, "Import, Spain"),
		              ("FIN-ADH-C2", "MSS-W-FL", "MSS-CC-FIN-M", 260, "Bag", 5, 90, "With the tiles"),
		              ("FIN-GRT-CG2", "MSS-W-FL", "MSS-CC-FIN-M", 90, "Bag", 30, 90, "With the tiles"))],
	})
	log("procurement plan: tiles required on site, PR dates worked back from a 90-day lead time")


def create_deliverables(award):
	if exists("Deliverable", {"awarded_quotation": award}):
		return
	for name, kind, status, due, submitted, approved in (
		("Flooring layout and setting-out drawings", "Drawing", "Approved", -100, -104, -98),
		("Porcelain tile sample and data sheet", "Material Submittal", "Approved", -115, -117, -112),
		("Method statement: floor tiling", "Method Statement", "Submitted", 3, -6, None),
		("Structural frame as-built drawings", "Drawing", "In Progress", -4, None, None),
		("Operation and maintenance manuals", "Handover", "Not Started", 200, None, None),
	):
		insert({"doctype": "Deliverable", "deliverable": name, "awarded_quotation": award, "deliverable_type": kind,
		        "status": status, "due_date": day(due), "responsible": user("pm"),
		        "submitted_date": day(submitted) if submitted else None,
		        "approved_date": day(approved) if approved else None})
	log("deliverables: 5 (2 approved, 1 with the client, 1 overdue, 1 not started)")


def create_variations(award):
	if exists("Variation Order", {"awarded_quotation": award}):
		return
	insert({"doctype": "Variation Order", "subject": "Entrance ramp and canopy, additional porcelain tiling",
	        "awarded_quotation": award, "vo_date": day(-60), "client_reference": "GPE/VO/004",
	        "variation_type": "Addition", "status": "Approved", "approved_date": day(-52), "time_extension_days": 10,
	        "items": [{"description": "Porcelain tiling, entrance ramp", "cost_head": "MSS-AR-FL", "qty": 85,
	                   "uom": "Square Meter", "rate": 46.00},
	                  {"description": "Steel canopy, supply and fix", "cost_head": "MSS-ES", "qty": 1,
	                   "uom": "Nos", "rate": 8200}]})
	insert({"doctype": "Variation Order", "subject": "Anti-slip R11 tiles in wet areas", "awarded_quotation": award,
	        "vo_date": day(-12), "client_reference": "GPE/VO/007", "variation_type": "Substitution",
	        "status": "Submitted to Client",
	        "items": [{"description": "Upgrade wet-area floors to R11 anti-slip", "cost_head": "MSS-AR-FL",
	                   "qty": 120, "uom": "Square Meter", "rate": 6.50}]})
	log("variation orders: 1 approved (+$12,110, 10 days), 1 with the client")
