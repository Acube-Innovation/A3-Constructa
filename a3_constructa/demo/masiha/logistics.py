# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Steps 9 to 13 and the deliveries of step 14.

The Spanish order ships in two lots: the first (two 40-foot containers under
one bill of lading) is cleared and received; the second is at Matadi under
customs, held by the missing duty receipt. The receipt records what arrived,
what was accepted and what was rejected, and the landed cost follows it,
including a demurrage bill that only arrived after the goods did.
"""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import flt

from a3_constructa.demo.masiha.common import (
	COMPANY,
	acc,
	as_user,
	at,
	comment,
	day,
	exists,
	insert,
	log,
	project,
	wh,
)

SUPPLIER = "Iberica Ceramica S.L."


def run():
	po = frappe.db.get_value("Purchase Order", {"supplier": SUPPLIER, "company": COMPANY, "docstatus": 1}, "name")
	supplier_updates(po)
	first = first_shipment(po)
	receipt = goods_receipt(po, first)
	landed_costs(receipt)
	second_shipment(po)
	site_deliveries()
	frappe.db.commit()


def supplier_updates(po):
	"""Step 9: what the expeditor records while the order is being made."""
	if frappe.db.count("Comment", {"reference_doctype": "Purchase Order", "reference_name": po,
	                               "comment_type": "Comment", "content": ["like", "Production progress%"]}):
		return
	for when, text in (
		(-80, "Production progress: 60% of the tiles pressed and fired. Photos received from Iberica."),
		(-68, "Production complete. FAT booked at the factory."),
		(-65, "FAT passed (report FAT/IBC/118): thickness 10 mm, water absorption 0.3%, slip R10. "
		      "Cargo ready for lot 1: 700 m2 of tiles and all adhesive."),
		(-58, "Packing list and dispatch advice received for lot 1: 2 x 40FT, 38 pallets. "
		      "Lot 2 (300 m2 and the grout) ready in three weeks."),
	):
		comment("Purchase Order", po, text, "logistics", at(when, 12))
	log("supplier updates: acknowledgement, production, FAT, readiness and dispatch advice on the order")


def _documents(rows):
	return [{"document_type": d, "document_no": n, "document_date": day(w), "issued_by": by,
	         "is_original_received": received, "received_date": day(w + 3) if received else None}
	        for d, n, w, by, received in rows]


def first_shipment(po):
	existing = exists("Shipment Tracking", {"purchase_order": po, "bl_no": "OSL-VLC-MTD-44812"})
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Shipment Tracking", "project": project(), "cost_head": "MSS-AR-FL", "purchase_order": po,
		"supplier": SUPPLIER, "shipment_type": "Import", "delivery_mode": "Direct to Warehouse",
		"status": "Received at Warehouse", "asn_no": "IBC-ASN-0418-1", "asn_date": day(-58),
		"expected_receipt_date": day(-12), "origin_port": "Valencia", "discharge_port": "Matadi",
		"service_route": "Valencia - Matadi", "shipping_line": "Oceanis Shipping Lines",
		"etd_origin": day(-55), "eta_discharge": day(-27), "ata_discharge": day(-25),
		"bl_no": "OSL-VLC-MTD-44812", "bl_date": day(-55), "cnf_agent": "Matadi Clearing & Forwarding SARL",
		"be_no": "BE/MAT/2026/10442", "be_date": day(-22), "duty_paid_amount": 3950, "clearance_date": day(-18),
		"container_return_date": day(-8), "demurrage_days": 4, "demurrage_amount": 640, "detention_amount": 0,
		"transporter": "Fleuve Congo Barges SARL", "lr_no": "FCB-LR-0871",
		"inland_despatch_date": day(-17), "inland_arrival_date": day(-12),
		# One bill of lading, two containers.
		"milestones": [
			{"milestone": "FAT Cleared", "reference_no": "FAT/IBC/118", "planned_date": day(-68), "actual_date": day(-65)},
			{"milestone": "Container Stuffed / Gate In", "reference_no": "OSLU-4471203", "planned_date": day(-60),
			 "actual_date": day(-58), "container_type": "40FT", "seal_no": "SL-509921"},
			{"milestone": "Container Stuffed / Gate In", "reference_no": "OSLU-4471788", "planned_date": day(-60),
			 "actual_date": day(-58), "container_type": "40FT", "seal_no": "SL-509934"},
			{"milestone": "Vessel Sailed", "reference_no": "OSL-VLC-MTD-44812", "planned_date": day(-56), "actual_date": day(-55)},
			{"milestone": "Arrived at Port", "reference_no": "MATADI", "planned_date": day(-28), "actual_date": day(-25)},
			{"milestone": "Customs Cleared", "reference_no": "BE/MAT/2026/10442", "planned_date": day(-23), "actual_date": day(-18)},
			{"milestone": "Despatched Inland", "reference_no": "FCB-LR-0871", "planned_date": day(-20), "actual_date": day(-17)},
			{"milestone": "Received at Warehouse", "reference_no": "Central Store Kinshasa", "planned_date": day(-15),
			 "actual_date": day(-12)},
		],
		"documents": _documents((
			("Commercial Invoice", "IBC-INV-7731", -57, SUPPLIER, 1),
			("Packing List", "IBC-PL-7731", -57, SUPPLIER, 1),
			("Bill of Lading", "OSL-VLC-MTD-44812", -55, "Oceanis Shipping Lines", 1),
			("Certificate of Origin", "COO/ES/VLC/22817", -57, "Camara de Comercio de Valencia", 1),
			("CNF Invoice", "MCF-INV-3302", -18, "Matadi Clearing & Forwarding SARL", 1),
			("Duty Payment Receipt", "DGDA/MAT/88120", -21, "DGDA Matadi", 1),
			("Delivery Order", "OSL-DO-44812", -19, "Oceanis Shipping Lines", 1),
		)),
	})
	doc.flags.ignore_permissions = True
	with as_user("logistics"):
		doc.insert()
		doc.submit()
	log(f"shipment {doc.name}: 2 x 40FT on one bill of lading, cleared, received; transit {doc.transit_days} days")
	return doc.name


def goods_receipt(po, shipment):
	existing = frappe.db.get_value("Purchase Receipt", {"supplier": SUPPLIER, "company": COMPANY, "docstatus": 1}, "name")
	if existing:
		return existing
	pr = make_purchase_receipt(po)
	pr.posting_date = day(-12)
	pr.set_posting_time = 1
	pr.rejected_warehouse = wh("Rejected Goods")
	pr.remarks = f"Lot 1 of {po}, shipment {shipment}. 10 m2 of WBS A tiles broken in transit; rejected."
	received = {("FIN-POR-600", "MSS-W-FL-A"): (600, 10), ("FIN-POR-600", "MSS-W-FL-B"): (100, 0),
	            ("FIN-ADH-C2", "MSS-W-FL-A"): (156, 0), ("FIN-ADH-C2", "MSS-W-FL-B"): (104, 0)}
	lines = []
	for row in pr.items:
		if (row.item_code, row.wbs) not in received:
			continue
		got, rejected = received[(row.item_code, row.wbs)]
		row.received_qty = got
		row.qty = got - rejected
		row.rejected_qty = rejected
		row.rejected_warehouse = wh("Rejected Goods")
		row.warehouse = wh("Central Store Kinshasa")
		lines.append(row)
	pr.items = lines
	with as_user("stores"):
		pr.insert()
		pr.submit()
	frappe.db.set_value("Shipment Tracking", shipment, "purchase_receipt", pr.name, update_modified=False)
	comment("Purchase Receipt", pr.name, "Inspection: 38 pallets counted. One pallet damaged, 10 m2 broken tiles "
	        "moved to Rejected Goods; supplier notified for a credit note. Balance on order: 300 m2 of WBS B "
	        "tiles and all grout (lot 2).", "stores", at(-12, 15))
	log(f"goods receipt {pr.name}: 700 m2 tiles (690 accepted, 10 rejected) and 260 bags adhesive")
	return pr.name


def landed_costs(receipt):
	if exists("Landed Cost Voucher", {"company": COMPANY, "docstatus": 1}):
		return
	for when, charges, note in (
		(-11, [("Ocean freight, 2 x 40FT Valencia-Matadi", 6800), ("Import duty (DGDA)", 3950),
		       ("Clearing and handling, Matadi", 1250), ("Barge Matadi-Kinshasa", 2100)],
		 "Landed cost at receipt."),
		(-3, [("Demurrage, 4 days over the free period", 640)],
		 "Demurrage invoice received after the GRN; added to the same receipt's cost."),
	):
		pr = frappe.get_doc("Purchase Receipt", receipt)
		lcv = frappe.new_doc("Landed Cost Voucher")
		lcv.company = COMPANY
		lcv.posting_date = day(when)
		lcv.distribute_charges_based_on = "Amount"
		lcv.append("purchase_receipts", {"receipt_document_type": "Purchase Receipt", "receipt_document": receipt,
		                                 "supplier": pr.supplier, "grand_total": pr.base_grand_total})
		lcv.get_items_from_purchase_receipts()
		for description, amount in charges:
			lcv.append("taxes", {"expense_account": acc("Import Freight and Clearing"), "description": description,
			                     "amount": amount})
		with as_user("logistics"):
			lcv.insert()
			lcv.submit()
		comment("Landed Cost Voucher", lcv.name, note, "logistics", at(when, 16))
	log("landed cost: $14,100 at receipt, $640 demurrage added later")


def second_shipment(po):
	if exists("Shipment Tracking", {"purchase_order": po, "bl_no": "OSL-VLC-MTD-45390"}):
		return
	doc = frappe.get_doc({
		"doctype": "Shipment Tracking", "project": project(), "cost_head": "MSS-AR-FL", "purchase_order": po,
		"supplier": SUPPLIER, "shipment_type": "Import", "delivery_mode": "Direct to Warehouse",
		"status": "Under Customs Clearance", "asn_no": "IBC-ASN-0418-2", "asn_date": day(-33),
		"expected_receipt_date": day(9), "origin_port": "Valencia", "discharge_port": "Matadi",
		"service_route": "Valencia - Matadi", "shipping_line": "Oceanis Shipping Lines",
		"etd_origin": day(-31), "eta_discharge": day(-5), "ata_discharge": day(-4), "bl_no": "OSL-VLC-MTD-45390",
		"bl_date": day(-31), "cnf_agent": "Matadi Clearing & Forwarding SARL", "be_no": "BE/MAT/2026/11207",
		"be_date": day(-2),
		"milestones": [
			{"milestone": "Container Stuffed / Gate In", "reference_no": "OSLU-4502116", "planned_date": day(-35),
			 "actual_date": day(-33), "container_type": "40FT", "seal_no": "SL-511702"},
			{"milestone": "Vessel Sailed", "reference_no": "OSL-VLC-MTD-45390", "planned_date": day(-32), "actual_date": day(-31)},
			{"milestone": "Arrived at Port", "reference_no": "MATADI", "planned_date": day(-4), "actual_date": day(-4)},
			{"milestone": "Customs Cleared", "reference_no": "BE/MAT/2026/11207", "planned_date": day(1)},
			{"milestone": "Received at Warehouse", "reference_no": "Central Store Kinshasa", "planned_date": day(9)},
		],
		"documents": _documents((
			("Commercial Invoice", "IBC-INV-7902", -33, SUPPLIER, 1),
			("Packing List", "IBC-PL-7902", -33, SUPPLIER, 1),
			("Bill of Lading", "OSL-VLC-MTD-45390", -31, "Oceanis Shipping Lines", 1),
			("Certificate of Origin", "COO/ES/VLC/23390", -33, "Camara de Comercio de Valencia", 0),
		)),
	})
	doc.flags.ignore_permissions = True
	with as_user("logistics"):
		doc.insert()
	comment("Shipment Tracking", doc.name, "At Matadi under customs. Outstanding: duty payment receipt (duty being "
	        "paid) and the original certificate of origin (courier). Submit is blocked until both are in.",
	        "logistics", at(-2, 11))
	log(f"shipment {doc.name}: 300 m2 and the grout, under customs, documents outstanding")


def site_deliveries():
	"""Step 14: the local order delivered straight to site, each lot on an authorized site receipt."""
	po = frappe.db.get_value("Purchase Order", {"supplier": "Congo Steel & Cement SARL", "company": COMPANY,
	                                            "docstatus": 1}, "name")
	if frappe.db.count("Purchase Receipt", {"supplier": "Congo Steel & Cement SARL", "docstatus": 1}):
		return
	for when, number, quantities in ((-72, "SMRN/MSS/0003", {"CEM-425-50": 700, "STL-Y16": 12}),
	                                 (-45, "SMRN/MSS/0009", {"CEM-425-50": 500, "STL-Y16": 8})):
		pr = make_purchase_receipt(po)
		pr.posting_date = day(when)
		pr.set_posting_time = 1
		pr.is_site_receipt = 1
		pr.site_receipt_no = number
		pr.receiving_site = "Mbandaka Site"
		for row in pr.items:
			row.qty = row.received_qty = quantities[row.item_code]
		with as_user("stores"):
			pr.insert()
			pr.submit()
		comment("Purchase Receipt", pr.name, f"Received at Mbandaka site by Chantal Mboyo against {number}; "
		        "delivery note signed by the site engineer.", "stores", at(when, 14))
	log("local deliveries: two site receipts (SMRN), order now fully received")
