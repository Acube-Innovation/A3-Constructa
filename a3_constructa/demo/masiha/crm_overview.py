# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-02: one case for each check on the CRM & Estimating overview.

- Tender due in 7 days with no quotation: a solar retrofit for the Wangata
  health centre, due in 4 days.
- Quotation below margin awaiting approval: the university library. Its tender
  BOQ is priced thin (4% overhead, 3% profit, 1% risk) and the lump-sum draft
  of P-02A is turned into the BOQ quotation, then sent for approval.
- Quotation expiring in 7 days: the Governor's residence, quoted 25 days ago
  for 30 days.
- Opportunity idle for 30 days: the Mbandaka-Bikoro road, untouched since its
  qualification meeting.
- Lost quotation without a reason: the central market roof, marked lost when
  the client went quiet, with no reason recorded.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, as_user, at, comment, day, insert, log, transition, user
from a3_constructa.demo.masiha.quotations import lump_sum

SOLAR = "Wangata health centre: solar power retrofit"
UNIVERSITY = "University library block"
# The university bill, priced: (ref, [(type, item, description, uom, qty/unit, wastage, output/day, rate, source)])
UNIVERSITY_SHEETS = {
	"1.1": [("Subcontract", None, "Frame subcontractor: concrete, formwork and rebar", "Cubic Meter", 1, None, None, 188, "Manual")],
	"1.2": [("Subcontract", None, "Blockwork gang, labour and blocks", "Square Meter", 1, None, None, 27.5, "Manual")],
	"2.1": [("Material", "FIN-POR-600", "Porcelain tile 600 x 600", "Square Meter", 1, 8, None, None, "Price List"),
	        ("Labour", None, "Tiling crew", None, None, None, 28, 145, "Manual")],
	"2.2": [("Subcontract", None, "Painting subcontractor", "Square Meter", 1, None, None, 1.55, "Manual")],
	"3.1": [("Material", "DW-ALW-1215", "Aluminium window 1200 x 1500", "Nos", 1, None, None, None, "Price List"),
	        ("Labour", None, "Window fixers (2)", None, None, None, 6, 70, "Manual")],
	"4.1": [("Material", "ELE-CBL-4", "Cable 4 mm²", "Meter", 1, 5, None, None, "Price List"),
	        ("Labour", None, "Electrician", None, None, None, 120, 45, "Manual")],
}


def run():
	if frappe.db.exists("Opportunity", {"title": SOLAR}):
		log("CRM overview cases already present")
		return
	made = [tender_due_unquoted(), below_margin_pending(), expiring_soon(), idle_opportunity(), lost_without_reason()]
	log("CRM overview cases: " + "; ".join(m for m in made if m))


def tender_due_unquoted():
	with as_user("sales"):
		o = insert({"doctype": "Opportunity", "opportunity_from": "Customer", "party_name": CUSTOMER, "company": COMPANY,
		            "title": SOLAR, "currency": "USD", "opportunity_amount": 280_000, "estimated_value": 280_000,
		            "sales_stage": "Proposal/Price Quote", "probability": 35, "sector": "Healthcare",
		            "enquiry_channel": "Public tender", "tender_due_date": day(4), "expected_closing": day(40),
		            "expected_award_date": day(40), "project_location": "Mbandaka Site", "opportunity_owner": user("sales"),
		            "transaction_date": day(-9)})
	frappe.db.set_value("Opportunity", o.name, "creation", at(-9, 10), update_modified=False)
	comment("Opportunity", o.name, "Tender documents in. Waiting on the PV supplier's price before we can quote.", "sales", at(-2, 15))
	return f"{o.name} due in 4 days, not quoted"


def below_margin_pending():
	from a3_constructa.overrides.quotation import update_from_boq

	opp = frappe.db.get_value("Opportunity", {"title": UNIVERSITY}, "name")
	boq = frappe.db.get_value("BOQ", {"opportunity": opp, "boq_stage": "Tender"}, "name") if opp else None
	draft = frappe.db.get_value("Quotation", {"opportunity": opp, "docstatus": 0}, "name") if opp else None
	if not (boq and draft):
		return None
	lines = {r.boq_ref: r.name for r in frappe.get_all("BOQ Item", filters={"parent": boq}, fields=["name", "boq_ref"])}
	with as_user("qs"):
		for ref, resources in UNIVERSITY_SHEETS.items():
			if frappe.db.exists("Estimate Sheet", {"boq": boq, "boq_item": lines[ref]}):
				continue
			sheet = frappe.new_doc("Estimate Sheet")
			sheet.boq, sheet.boq_item = boq, lines[ref]
			for rtype, item, desc, uom, qty, wastage, output, rate, source in resources:
				sheet.append("resources", {"resource_type": rtype, "item_code": item, "description": desc, "uom": uom,
				                           "qty_per_unit": qty, "wastage_percent": wastage, "output_per_day": output,
				                           "rate": rate, "rate_source": source})
			sheet.fetch_prices()
			sheet.flags.ignore_permissions = True
			sheet.insert()
		b = frappe.get_doc("BOQ", boq)
		b.update({"overhead_percent": 4, "profit_percent": 3, "risk_percent": 1})
		b.flags.ignore_permissions = True
		b.save()
		# The lump-sum placeholder of P-02A becomes the priced BOQ quotation.
		q = frappe.get_doc("Quotation", draft)
		q.boq = boq
		q.flags.ignore_permissions = True
		q.save()
		result = update_from_boq(draft)
	comment("BOQ", boq, "Priced thin to win the library: 4% overhead, 3% profit, 1% risk.", "qs", at(-1, 16))
	transition("Quotation", draft, "Submit for Approval", "sales", at(0, 10),
	           f"Margin {result['margin_percent']:.1f}%, under our floor; the university has two other bidders. Albert, please decide.")
	return f"{draft} from {boq}: ${result['after']:,.2f}, margin {result['margin_percent']:.1f}%, pending approval"


def expiring_soon():
	lead = frappe.db.get_value("Lead", {"company_name": "Résidence du Gouverneur"}, "name")
	if not lead:
		return None
	q = lump_sum("Lead", lead, "Residence refurbishment: roof, finishes and services, lump sum", 335_000, -25)
	comment("Quotation", q.name, "Client is comparing two bids; promised an answer 'next week'.", "sales", at(-3, 11))
	return f"{q.name} expires {q.valid_till}"


def idle_opportunity():
	name = frappe.db.get_value("Opportunity", {"title": "Route Mbandaka-Bikoro rehabilitation, lot 2"}, "name")
	if not name:
		return None
	frappe.db.set_value("Opportunity", name, "modified", at(-36, 16), update_modified=False)
	return f"{name} untouched for 36 days"


def lost_without_reason():
	from a3_constructa.overrides.quotation import declare_lost

	lead = frappe.db.get_value("Lead", {"company_name": "Marché central de Mbandaka"}, "name")
	if not lead:
		return None
	q = lump_sum("Lead", lead, "Central market roof and stalls, design and build, lump sum", 1_640_000, -40)
	with as_user("sales"):
		declare_lost(q.name, [], [], None, None)
	frappe.db.set_value("Quotation", q.name, "modified", at(-6, 9), update_modified=False)
	return f"{q.name} lost, no reason recorded"
