# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02C: the hospital tender's rates, built up from resources.

Six lines of BOQ-2026-0007 get an Estimate Sheet: porcelain tiling (tile,
adhesive and grout from the price list, the tiling crew of the test-data
standard, and sea freight from the Valencia-Matadi contract), reinforced
concrete, rebar, excavation (excavator and its fuel), theatre vinyl by a
specialist subcontractor, and cable. Then the porcelain supplier's price rises
from $18.50 to $19.20 a m² and "Re-price sheets" carries it into the estimate.
The other eight lines are left to price.
"""

import frappe

from a3_constructa.a3_constructa.doctype.estimate_sheet.estimate_sheet import reprice_sheets
from a3_constructa.demo.masiha.common import BUYING_PRICE_LIST, as_user, at, comment, log

TENDER = "Hospital extension: maternity and theatre block"
NEW_TILE_PRICE = 19.20

# boq_ref -> resources: (type, item, description, uom, qty per unit, wastage %, output/day, rate, source)
SHEETS = {
	"B/03/12": [
		("Material", "FIN-POR-600", "Porcelain tile 600 x 600 R10", "Square Meter", 1, 8, None, None, "Price List"),
		("Material", "FIN-ADH-C2", "Tile adhesive C2TE, 25 kg", "Bag", 0.26, 5, None, None, "Price List"),
		("Material", "FIN-GRT-CG2", "Tile grout CG2, 5 kg", "Bag", 0.09, 5, None, None, "Price List"),
		("Labour", None, "Tiling foreman", None, None, None, 28, 45, "Manual"),
		("Labour", None, "Tilers (2)", None, None, None, 28, 70, "Manual"),
		("Labour", None, "Helpers (2)", None, None, None, 28, 30, "Manual"),
		("Other", None, "Sea freight, 40FT Valencia-Matadi (about 1,400 m² a container)", None, 1 / 1400, None, None, None, "Freight Rate Contract"),
	],
	"A/02/03": [
		("Material", "CEM-425-50", "Cement CEM II 42.5N, 50 kg", "Bag", 7, 3, None, None, "Price List"),
		("Material", None, "Sand and 20 mm aggregate, delivered to site", "Cubic Meter", 1.25, 5, None, 32, "Manual"),
		("Labour", None, "Concrete gang (6)", None, None, None, 12, 150, "Manual"),
		("Equipment", None, "Mixer and poker vibrators", None, None, None, 12, 55, "Manual"),
		("Subcontract", None, "Formwork to ground beams (supply and fix)", "Square Meter", 4.5, None, None, 9.5, "Manual"),
	],
	"A/02/04": [
		("Material", "STL-Y16", "Rebar Y16", "Tonne", 1, 5, None, None, "Price List"),
		("Labour", None, "Steel fixers (2)", None, None, None, 0.8, 80, "Manual"),
	],
	"A/01/02": [
		("Equipment", None, "Excavator 20 t (HEQ-0001), 8 h at $65", None, None, None, 180, 520, "Manual"),
		("Equipment", None, "Fuel, 14 L/h x 8 h at $1.60", None, None, None, 180, 179.2, "Manual"),
		("Labour", None, "Banksman", None, None, None, 180, 15, "Manual"),
	],
	"B/03/14": [
		("Subcontract", None, "Specialist flooring: welded anti-bacterial vinyl, coved", "Square Meter", 1, None, None, 42, "Manual"),
	],
	"C/01/04": [
		("Material", "ELE-CBL-4", "Copper cable 4 mm²", "Meter", 1, 3, None, None, "Price List"),
		("Labour", None, "Electrician", None, None, None, 120, 40, "Manual"),
	],
}


def run():
	opp = frappe.db.get_value("Opportunity", {"title": TENDER}, "name")
	boq = frappe.db.get_value("BOQ", {"opportunity": opp, "boq_stage": "Tender"}, "name") if opp else None
	if not boq:
		log("no hospital tender BOQ; run the tender stage first")
		return
	if frappe.db.exists("Estimate Sheet", {"boq": boq}):
		log("estimate sheets already present")
		return
	lines = {r.boq_ref: r.name for r in frappe.get_all("BOQ Item", filters={"parent": boq}, fields=["name", "boq_ref"])}
	made = []
	with as_user("qs"):
		for ref, resources in SHEETS.items():
			sheet = frappe.new_doc("Estimate Sheet")
			sheet.boq, sheet.boq_item = boq, lines[ref]
			for rtype, item, desc, uom, qty, wastage, output, rate, source in resources:
				sheet.append("resources", {"resource_type": rtype, "item_code": item, "description": desc, "uom": uom,
				                           "qty_per_unit": qty, "wastage_percent": wastage, "output_per_day": output,
				                           "rate": rate, "rate_source": source})
			sheet.fetch_prices()
			sheet.flags.ignore_permissions = True
			sheet.insert()
			made.append(f"{sheet.name} {ref} ${sheet.unit_cost:,.2f}")

	# The tile supplier's new price list, then re-price the open sheets.
	price = frappe.db.get_value("Item Price", {"item_code": "FIN-POR-600", "price_list": BUYING_PRICE_LIST}, "name")
	before = frappe.db.get_value("Item Price", price, "price_list_rate")
	frappe.db.set_value("Item Price", price, "price_list_rate", NEW_TILE_PRICE)
	with as_user("qs"):
		changes = reprice_sheets(boq)
	comment("BOQ", boq, f"Porcelain price list up from ${before:.2f} to ${NEW_TILE_PRICE:.2f} a m²; sheets re-priced "
	        f"({', '.join(c['boq_ref'] for c in changes)}).", "qs", at(-1, 11))
	log("estimate sheets: " + "; ".join(made) + f". Re-priced after tile price rise: {len(changes)} sheet(s)")
