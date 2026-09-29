# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Steps 5 to 7: purchase requests, their verification and approval, and the buyer's queue.

The flooring request is raised from the BOQ exactly as Get Items From > BOQ
raises it: the porcelain line comes in twice, 600 m2 on WBS A and 400 m2 on
WBS B, each with its cost code and a link back to the BOQ line. It is returned
for correction once before stores verify it and the project manager approves.
"""

import frappe
from frappe.utils import getdate

from a3_constructa.api.boq_procurement import get_request_lines
from a3_constructa.demo.masiha.common import (
	AWARD_TITLE,
	COMPANY,
	as_user,
	assign,
	at,
	comment,
	day,
	exists,
	insert,
	log,
	project,
	transition,
	wh,
)

CENTRAL = "Central Store Kinshasa"
SITE = "Mbandaka Site Store"


def run():
	create_opening_stock()
	award = frappe.db.get_value("Awarded Quotation", {"title": AWARD_TITLE, "company": COMPANY}, "name")
	lines = get_request_lines(awarded_quotation=award, company=COMPANY)
	flooring = create_flooring_request(lines)
	structural = create_structural_request(lines)
	excavator = create_excavator_request()
	create_rejected_request()
	create_transfer_request()
	route_to_buyer(flooring, structural, excavator)
	frappe.db.commit()


def create_opening_stock():
	"""Paint already in the central store, so a request can be met by transfer (step 6)."""
	if exists("Stock Entry", {"company": COMPANY, "stock_entry_type": "Material Receipt", "docstatus": 1}):
		return
	insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Receipt",
	        "posting_date": day(-150), "set_posting_time": 1, "remarks": "Opening balance, central store",
	        "items": [{"item_code": "PNT-EMU-20", "qty": 60, "basic_rate": 64, "t_warehouse": wh(CENTRAL)}]},
	       submit=True)
	log("opening stock: 60 pails of paint in the central store")


def _request(title, when, rows, kind="Purchase", from_store=None):
	with as_user("requester"):
		doc = frappe.get_doc({
			"doctype": "Material Request", "material_request_type": kind, "company": COMPANY,
			"title": title, "transaction_date": day(when), "schedule_date": rows[0]["schedule_date"],
			"set_from_warehouse": wh(from_store) if from_store else None, "items": rows,
		})
		doc.insert()
	return doc.name


def _row(item, qty, uom, wbs, cost_code, need_by, store=CENTRAL, line=None, cost_head=None, rate=0):
	row = {"item_code": item, "qty": qty, "uom": uom, "schedule_date": day(need_by), "warehouse": wh(store),
	       "project": project(), "wbs": wbs, "cost_code": cost_code, "cost_head": cost_head, "rate": rate}
	if line:
		row.update({"boq": line["boq"], "boq_item": line["boq_item"], "cost_head": line["cost_head"],
		            "conversion_factor": line["conversion_factor"], "rate": line["rate"]})
	return row


def create_flooring_request(lines) -> str:
	existing = exists("Material Request", {"title": "Flooring materials, ground and first floor"})
	if existing:
		log(f"flooring request already present: {existing}")
		return existing

	# The porcelain, adhesive and grout lines of the flooring BOQ, one per WBS.
	rows = [_row(l["item_code"], l["to_request"], l["uom"], l["wbs"], l["cost_code"], -52, line=l)
	        for l in lines
	        if l["item_code"] in ("FIN-POR-600", "FIN-ADH-C2", "FIN-GRT-CG2") and l["wbs"] in ("MSS-W-FL-A", "MSS-W-FL-B")]
	# Site consumables no BOQ line carries, bought for cash later.
	rows += [_row("FIN-DSC-230", 10, "Nos", "MSS-W-FL", "MSS-CC-SITE", -80, cost_head="MSS-AR-FL", rate=22.0),
	         _row("FIN-SPC-3", 20, "Box", "MSS-W-FL", "MSS-CC-SITE", -80, cost_head="MSS-AR-FL", rate=4.5)]
	# First submitted with a required date the supplier lead time cannot meet.
	for row in rows[:6]:
		row["schedule_date"] = day(-95)
	name = _request("Flooring materials, ground and first floor", -112, rows)

	transition("Material Request", name, "Submit for Verification", "requester", at(-112, 10))
	transition("Material Request", name, "Return for Correction", "stores", at(-111, 9),
	           "Returned for correction: imported tiles need about 60 days. Set 'Required By' for the "
	           "porcelain, adhesive and grout to the planned site date, and keep Central Store Kinshasa "
	           "as the destination for imports.")
	with as_user("requester"):
		doc = frappe.get_doc("Material Request", name)
		for row in doc.items:
			if row.item_code in ("FIN-POR-600", "FIN-ADH-C2", "FIN-GRT-CG2"):
				row.schedule_date = getdate(day(-52))
		doc.schedule_date = getdate(day(-80))
		doc.save()
	comment("Material Request", name, "Corrected the required-by dates as advised.", "requester", at(-110, 10))
	transition("Material Request", name, "Submit for Verification", "requester", at(-110, 11))
	transition("Material Request", name, "Verify Stock", "stores", at(-109, 10),
	           "Stock verified: no porcelain, adhesive or grout in any store and none on order. Purchase required.")
	transition("Material Request", name, "Approve", "pm", at(-108, 15),
	           "Approved. Within flooring BOQ revision 1; the 600/400 m2 split follows the WBS allocation.")
	log(f"flooring request {name}: 8 lines, returned once, verified, approved")
	return name


def create_structural_request(lines) -> str:
	existing = exists("Material Request", {"title": "Cement and reinforcement, frame"})
	if existing:
		return existing
	by_item = {l["item_code"]: l for l in lines if l["wbs"] == "MSS-W-ES"}
	rows = [_row("CEM-425-50", 1200, "Bag", "MSS-W-ES", "MSS-CC-STR-M", -70, store="Mbandaka Site Store",
	             line=by_item["CEM-425-50"]),
	        _row("STL-Y16", 20, "Tonne", "MSS-W-ES", "MSS-CC-STR-M", -70, store="Mbandaka Site Store",
	             line=by_item["STL-Y16"])]
	name = _request("Cement and reinforcement, frame", -105, rows)
	transition("Material Request", name, "Submit for Verification", "requester", at(-105, 9))
	transition("Material Request", name, "Verify Stock", "stores", at(-104, 14), "No stock at site; purchase locally.")
	transition("Material Request", name, "Approve", "pm", at(-103, 10), "Approved against the structural BOQ.")
	log(f"structural request {name}: cement and rebar, delivered to site")
	return name


def create_excavator_request() -> str:
	existing = exists("Material Request", {"title": "Excavator 20 t for earthworks"})
	if existing:
		return existing
	rows = [_row("EQ-EXC-20T", 1, "Nos", "MSS-W-ES", "MSS-CC-PLT", -65, cost_head="MSS-ES", rate=145000)]
	name = _request("Excavator 20 t for earthworks", -100, rows)
	transition("Material Request", name, "Submit for Verification", "requester", at(-100, 9))
	transition("Material Request", name, "Verify Stock", "stores", at(-99, 11), "No suitable machine in the fleet.")
	transition("Material Request", name, "Approve", "pm", at(-98, 16), "Approved: capital purchase, to be capitalised.")
	log(f"equipment request {name}: one excavator (an asset)")
	return name


def create_rejected_request():
	if exists("Material Request", {"title": "Interior paint, block A"}):
		return
	rows = [_row("PNT-EMU-20", 40, "Nos", "MSS-W-PT", "MSS-CC-PNT-M", -85, store=SITE, cost_head="MSS-AR-PT", rate=64)]
	name = _request("Interior paint, block A", -98, rows)
	transition("Material Request", name, "Submit for Verification", "requester", at(-98, 9))
	transition("Material Request", name, "Verify Stock", "stores", at(-97, 10),
	           "60 pails of the same paint are in Central Store Kinshasa.")
	transition("Material Request", name, "Reject", "pm", at(-97, 15),
	           "Rejected: stock is available in the central store. Raise a transfer instead of a purchase.")
	log(f"rejected request {name}: stock existed, so it became a transfer")


def create_transfer_request():
	existing = exists("Material Request", {"title": "Interior paint, block A (transfer)"})
	if existing:
		return existing
	rows = [_row("PNT-EMU-20", 40, "Nos", "MSS-W-PT", "MSS-CC-PNT-M", -85, store=SITE, cost_head="MSS-AR-PT")]
	name = _request("Interior paint, block A (transfer)", -96, rows, kind="Material Transfer", from_store=CENTRAL)
	transition("Material Request", name, "Submit for Verification", "requester", at(-96, 9))
	transition("Material Request", name, "Verify Stock", "stores", at(-96, 11), "Available in Central Store Kinshasa.")
	transition("Material Request", name, "Approve", "pm", at(-96, 14))

	from erpnext.stock.doctype.material_request.material_request import make_stock_entry

	with as_user("stores"):
		entry = make_stock_entry(name)
		entry.posting_date = day(-90)
		entry.set_posting_time = 1
		for row in entry.items:
			row.update({"project": project(), "cost_head": "MSS-AR-PT", "wbs": "MSS-W-PT", "cost_code": "MSS-CC-PNT-M"})
		entry.insert()
		entry.submit()
	log(f"transfer request {name}: met from stock by {entry.name}, no purchase")


def route_to_buyer(flooring, structural, excavator):
	"""Step 7: the approved lines reach the buyer, each with the route it will take."""
	routes = {"FIN-POR-600": "International PO", "FIN-ADH-C2": "International PO", "FIN-GRT-CG2": "International PO",
	          "FIN-DSC-230": "Cash Purchase", "FIN-SPC-3": "Cash Purchase", "CEM-425-50": "Local PO",
	          "STL-Y16": "Local PO", "EQ-EXC-20T": "Local PO"}
	for name, when, note in (
		(flooring, -107, "Porcelain, adhesive and grout: international RFQ (Spain, China). Discs and spacers: cash purchase at site."),
		(structural, -102, "Local RFQ for cement and rebar, delivered direct to site."),
		(excavator, -97, "Local purchase from the equipment dealer; asset to be registered on receipt."),
	):
		for row in frappe.get_all("Material Request Item", filters={"parent": name}, fields=["name", "item_code"]):
			frappe.db.set_value("Material Request Item", row.name, "procurement_route", routes.get(row.item_code),
			                    update_modified=False)
		if not exists("ToDo", {"reference_type": "Material Request", "reference_name": name, "status": "Open"}):
			assign("Material Request", name, "buyer", "procurement", at(when, 9), note)
	log("approved requests assigned to the buyer, each line given its procurement route")
