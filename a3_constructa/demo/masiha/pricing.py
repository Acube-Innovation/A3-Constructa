# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02D: the hospital tender priced to a selling total.

The remaining eight lines get their estimate sheets, the four preliminaries
go in as allowance lines under a new Preliminaries cost head, and the bid
carries 8% overhead, 7% profit, 3% risk and a $20,000 contingency.
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, at, comment, insert, log

TENDER = "Hospital extension: maternity and theatre block"
PRELIMS_HEAD = "MSS-PRE"

PRELIMINARIES = [
	("P/01", "Site set-up, welfare cabins and site office, 18 months", 18_000),
	("P/02", "Site supervision: site engineer and HSE officer, 18 months", 34_000),
	("P/03", "Insurances: contractor's all risks and third party", 7_500),
	("P/04", "Temporary works: hoarding, scaffolding and propping", 12_000),
]
MARKUPS = {"overhead_percent": 8, "profit_percent": 7, "risk_percent": 3, "contingency_amount": 20_000}

# The lines P-02C left unpriced: (type, item, description, uom, qty per unit, wastage, output/day, rate, source)
SHEETS = {
	"A/01/01": [("Equipment", None, "Dozer D6 with operator", None, None, None, 1200, 640, "Manual"),
	            ("Labour", None, "Labourers (2)", None, None, None, 1200, 30, "Manual")],
	"A/02/01": [("Material", "CEM-425-50", "Cement CEM II 42.5N, 50 kg", "Bag", 4.5, 3, None, None, "Price List"),
	            ("Material", None, "Sand and 20 mm aggregate, delivered", "Cubic Meter", 1.1, 5, None, 32, "Manual"),
	            ("Labour", None, "Concrete gang (6)", None, None, None, 10, 150, "Manual")],
	"A/03/01": [("Material", "CEM-425-50", "Cement CEM II 42.5N, 50 kg", "Bag", 1, 2, None, None, "Price List")],
	"B/01/02": [("Material", "DW-ALW-1215", "Aluminium window 1200 x 1500", "Nos", 1, None, None, None, "Price List"),
	            ("Labour", None, "Window fixers (2)", None, None, None, 6, 70, "Manual")],
	"B/01/05": [("Material", "DW-DOR-FD90", "Fire door FD90 with frame", "Nos", 1, None, None, None, "Price List"),
	            ("Labour", None, "Carpenter", None, None, None, 4, 40, "Manual")],
	"B/04/02": [("Material", "PNT-EMU-20", "Emulsion paint, 20 L pail", "Nos", 0.0125, 5, None, None, "Price List"),
	            ("Labour", None, "Painters (2)", None, None, None, 80, 60, "Manual")],
	"C/02/01": [("Subcontract", None, "Medical gas specialist: outlet, pipework and testing", "Nos", 1, None, None, 1250, "Manual")],
	"C/03/01": [("Subcontract", None, "Generator 250 kVA: supply, install, commission", "Nos", 1, None, None, 68_000, "Manual")],
}


def run():
	opp = frappe.db.get_value("Opportunity", {"title": TENDER}, "name")
	boq_name = frappe.db.get_value("BOQ", {"opportunity": opp, "boq_stage": "Tender"}, "name") if opp else None
	if not boq_name:
		log("no hospital tender BOQ; run the tender and estimates stages first")
		return
	if frappe.db.get_value("BOQ", boq_name, "profit_percent"):
		log("hospital tender already priced")
		return
	if not frappe.db.exists("Cost Head", PRELIMS_HEAD):
		insert({"doctype": "Cost Head", "cost_head_code": PRELIMS_HEAD, "cost_head_name": "Preliminaries",
		        "project": frappe.db.get_value("Cost Head", "MSS-ES", "project"), "is_preliminaries": 1})

	lines = {r.boq_ref: r.name for r in frappe.get_all("BOQ Item", filters={"parent": boq_name}, fields=["name", "boq_ref"])}
	with as_user("qs"):
		for ref, resources in SHEETS.items():
			if frappe.db.exists("Estimate Sheet", {"boq": boq_name, "boq_item": lines[ref]}):
				continue
			sheet = frappe.new_doc("Estimate Sheet")
			sheet.boq, sheet.boq_item = boq_name, lines[ref]
			for rtype, item, desc, uom, qty, wastage, output, rate, source in resources:
				sheet.append("resources", {"resource_type": rtype, "item_code": item, "description": desc, "uom": uom,
				                           "qty_per_unit": qty, "wastage_percent": wastage, "output_per_day": output,
				                           "rate": rate, "rate_source": source})
			sheet.fetch_prices()
			sheet.flags.ignore_permissions = True
			sheet.insert()

		boq = frappe.get_doc("BOQ", boq_name)
		for ref, description, amount in PRELIMINARIES:
			boq.append("items", {"is_allowance": 1, "boq_ref": ref, "cost_head": PRELIMS_HEAD, "description": description, "amount": amount})
		boq.update(MARKUPS)
		boq.flags.ignore_permissions = True
		boq.save()
	comment("BOQ", boq_name, f"Priced: cost ${boq.cost_total:,.0f}, selling ${boq.selling_total:,.0f}, margin {boq.margin_percent:.1f}%. "
	        "Ready for the quotation.", "qs", at(-1, 17))
	log(f"{boq_name}: cost ${boq.cost_total:,.2f} (preliminaries ${boq.preliminaries_total:,.0f}), selling ${boq.selling_total:,.2f}, "
	    f"margin {boq.margin_percent:.1f}%, {boq.unpriced_lines} unpriced")
