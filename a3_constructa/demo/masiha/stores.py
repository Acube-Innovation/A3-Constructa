# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Steps 16 to 18: from the central store to the floor it is laid on.

The client's MIN is the dispatch: stock leaves Central Store Kinshasa into the
transit store and stays visible there, by barge, until the site receives it
against that same entry (the MRN). Short-received stock remains in transit for
investigation. On site, material is issued to its WBS and cost code, which is
the moment it becomes project cost; unused paint goes back to the store.
"""

import frappe
from erpnext.stock.doctype.material_request.material_request import make_stock_entry
from erpnext.stock.doctype.stock_entry.stock_entry import make_stock_in_entry

from a3_constructa.demo.masiha.common import (
	COMPANY,
	as_user,
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

REQUIREMENT = "Ground-floor tiling materials to site"
TAGS_A = {"cost_head": "MSS-AR-FL", "wbs": "MSS-W-FL-A", "cost_code": "MSS-CC-FIN-M"}


def run():
	requirement = site_requirement()
	dispatch = warehouse_dispatch(requirement)
	site_receipt(dispatch)
	consumption()
	site_return()
	frappe.db.commit()


def site_requirement():
	existing = exists("Material Request", {"title": REQUIREMENT, "company": COMPANY})
	if existing:
		return existing
	rows = [{"item_code": item, "qty": qty, "schedule_date": day(-2), "warehouse": wh("Mbandaka Site Store"),
	         "project": project(), **TAGS_A} for item, qty in (("FIN-POR-600", 590), ("FIN-ADH-C2", 156))]
	with as_user("requester"):
		doc = frappe.get_doc({"doctype": "Material Request", "material_request_type": "Material Transfer",
		                      "company": COMPANY, "title": REQUIREMENT, "transaction_date": day(-11),
		                      "schedule_date": day(-2), "set_from_warehouse": wh("Central Store Kinshasa"),
		                      "items": rows})
		doc.insert()
	transition("Material Request", doc.name, "Submit for Verification", "requester", at(-11, 9))
	transition("Material Request", doc.name, "Verify Stock", "stores", at(-11, 14), "590 m2 accepted stock in Central Store.")
	transition("Material Request", doc.name, "Approve", "pm", at(-10, 9), "Approved for dispatch by barge.")
	return doc.name


def warehouse_dispatch(requirement):
	existing = exists("Stock Entry", {"company": COMPANY, "stock_entry_type": "Warehouse Dispatch (MIN)", "docstatus": 1})
	if existing:
		return existing
	entry = make_stock_entry(requirement)
	entry.stock_entry_type = "Warehouse Dispatch (MIN)"
	entry.add_to_transit = 1
	entry.posting_date = day(-9)
	entry.set_posting_time = 1
	entry.project = project()
	entry.mode_of_transport = "Barge"
	entry.transporter = "Fleuve Congo Barges SARL"
	entry.vehicle_no = "BRG-207 (convoy 12)"
	entry.lr_no = "FCB-LR-0912"
	entry.remarks = f"Dispatch against site requirement {requirement}: ground-floor tiles and adhesive, WBS A."
	for row in entry.items:
		row.t_warehouse = wh("Goods In Transit")
		row.update(TAGS_A)
		row.project = project()
	with as_user("stores"):
		entry.insert()
		entry.submit()
	log(f"dispatch (MIN) {entry.name}: 590 m2 tiles and 156 bags into transit by barge BRG-207")
	return entry.name


def site_receipt(dispatch):
	if exists("Stock Entry", {"company": COMPANY, "outgoing_stock_entry": dispatch, "docstatus": 1}):
		return
	entry = make_stock_in_entry(dispatch)
	entry.stock_entry_type = "Material Receipt Note (MRN)"
	entry.posting_date = day(-4)
	entry.set_posting_time = 1
	entry.project = project()
	received = {"FIN-POR-600": 560, "FIN-ADH-C2": 150}
	for row in entry.items:
		row.qty = received[row.item_code]
		row.t_warehouse = wh("Mbandaka Site Store")
		row.update(TAGS_A)
		row.project = project()
	with as_user("stores"):
		entry.insert()
		entry.submit()
	comment("Stock Entry", entry.name, "Received at Mbandaka against the dispatch: 560 of 590 m2 tiles and 150 of 156 "
	        "bags. 30 m2 (one pallet) and 6 bags not found on unloading; left in transit and reported to Fleuve "
	        "Congo Barges for investigation.", "stores", at(-4, 16))
	log(f"site receipt (MRN) {entry.name}: 560 m2 and 150 bags received; 30 m2 and 6 bags still in transit")


def consumption():
	if exists("Stock Entry", {"company": COMPANY, "stock_entry_type": "Material Issue Note (MIN)", "docstatus": 1}):
		return
	issues = [
		("FIN-POR-600", 380, TAGS_A, "Laid: ground floor zones 1-3"),
		("FIN-ADH-C2", 98, TAGS_A, "Used with the tiles laid"),
		("PNT-EMU-20", 25, {"cost_head": "MSS-AR-PT", "wbs": "MSS-W-PT", "cost_code": "MSS-CC-PNT-M"}, "Walls, block A"),
	]
	insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Issue Note (MIN)",
	        "posting_date": day(-2), "set_posting_time": 1, "project": project(),
	        "remarks": "Issued from site stock to the works: each line posts to its cost code's project account.",
	        "items": [{"item_code": item, "qty": qty, "s_warehouse": wh("Mbandaka Site Store"), "project": project(),
	                   "description": note, **tags} for item, qty, tags, note in issues]}, submit=True)
	log("site consumption: 380 m2 tiles and 98 bags to WBS A, 25 pails of paint to painting")


def site_return():
	if exists("Stock Entry", {"company": COMPANY, "stock_entry_type": "Site Material Return", "docstatus": 1}):
		return
	insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Site Material Return",
	        "posting_date": day(-1), "set_posting_time": 1, "project": project(),
	        "remarks": "Unused paint back to the central store.",
	        "items": [{"item_code": "PNT-EMU-20", "qty": 5, "s_warehouse": wh("Mbandaka Site Store"),
	                   "t_warehouse": wh("Central Store Kinshasa"), "project": project(), "cost_head": "MSS-AR-PT",
	                   "wbs": "MSS-W-PT", "cost_code": "MSS-CC-PNT-M"}]}, submit=True)
	log("site return: 5 pails of paint back to the central store")
