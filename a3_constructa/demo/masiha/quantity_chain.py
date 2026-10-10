# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-13B: the quantity chain, and consumption against the BOQ.

The Administrative Centre's budget lines carry the wastage they were priced
with on the tender's build-ups: 8% on porcelain tiles, 5% on adhesive and
grout, 3% on cement, 5% on paint. Two issues from the site store then show
the two kinds of over-use:

- 24 bags of adhesive bedded the lobby feature wall (WBS Architectural works),
  where the BOQ allows 22 bags + 5% = 23.1: 0.9 of a bag over, to explain;
- 4 boxes of 3 mm tile spacers on the ground floor, which the BOQ never
  measured at all: unbudgeted, so all of it is over-use.

The cement issued to Architectural works (43 bags, P-01D) shows in the chain
as issued to a WBS whose BOQ has no cement: booked to the wrong WBS or a gap
in the bill.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, comment, day, exists, insert, log, project, wh

DEMO_BOQS = ("BOQ-2026-0001", "BOQ-2026-0003", "BOQ-2026-0005-1", "BOQ-2026-0006")
WASTAGE = {"FIN-POR-600": 8, "FIN-ADH-C2": 5, "FIN-GRT-CG2": 5, "CEM-425-50": 3, "PNT-EMU-20": 5}
MARK = "Lobby feature wall"


def run():
	p = project()
	boqs = frappe.get_all("BOQ", filters={"project": p, "docstatus": 1, "name": ["in", DEMO_BOQS]}, pluck="name")
	set_wastage = 0
	for line in frappe.get_all("BOQ Item", filters={"parent": ["in", boqs], "item_code": ["in", list(WASTAGE)], "wastage_percent": 0},
	                           fields=["name", "item_code"]):
		frappe.db.set_value("BOQ Item", line.name, "wastage_percent", WASTAGE[line.item_code], update_modified=False)
		set_wastage += 1
	log(f"wastage set on {set_wastage} budget lines (tiles 8%, adhesive and grout 5%, cement 3%, paint 5%)")

	if exists("Stock Entry", {"company": COMPANY, "docstatus": 1, "remarks": ["like", f"{MARK}%"]}):
		log("over-use issues already present")
		return
	entry = insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Issue Note (MIN)",
	                "posting_date": day(-1), "set_posting_time": 1, "project": p,
	                "remarks": f"{MARK} and ground-floor setting out: adhesive bedded the feature wall; spacers for the tiling.",
	                "items": [
		                {"item_code": "FIN-ADH-C2", "qty": 24, "s_warehouse": wh("Mbandaka Site Store"), "project": p,
		                 "cost_head": "MSS-AR", "wbs": "MSS-W-AR", "cost_code": "MSS-CC-FIN-M",
		                 "description": "Lobby feature wall: stone cladding bedded on adhesive"},
		                {"item_code": "FIN-SPC-3", "qty": 4, "s_warehouse": wh("Mbandaka Site Store"), "project": p,
		                 "cost_head": "MSS-AR-FL", "wbs": "MSS-W-FL-A", "cost_code": "MSS-CC-FIN-M",
		                 "description": "Tile spacers, ground floor zones 4-5"},
	                ]}, submit=True)
	comment("Stock Entry", entry.name, "Feature wall took 24 bags against 22 in the bill: the stone is thicker than drawn. "
	        "Spacers were never measured in the BOQ. Both raised with the QS.", "pm", None)
	log(f"{entry.name}: 24 bags adhesive to the lobby (allowed 23.1) and 4 boxes of spacers (not in the BOQ)")
