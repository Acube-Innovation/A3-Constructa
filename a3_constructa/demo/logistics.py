# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo logistics: an import shipment from Shanghai, and the goods receipt."""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import company, day, log, warehouse
from a3_constructa.demo.masters import _project, university_head

MILESTONES = [
	("FAT Cleared", "FAT/2026/114", -78, -76, "40FT", None),
	("Container Stuffed / Gate In", "CRLU-2298451", -74, -72, "40FT", "SL-88214"),
	("Vessel Sailed", "BL-CRL-55120", -70, -70, None, None),
	("Arrived at Port", "BL-CRL-55120", -30, -26, None, None),
	("Customs Cleared", "BE/MAT/8842", -24, -18, None, None),
	("Despatched Inland", "LR-4471", -16, -15, None, None),
]

DOCUMENTS = [
	("Certificate of Origin", "COO/CN/7741", -72, "Shanghai Chamber of Commerce", 1),
	("CNF Invoice", "INV-CRL-9930", -70, "Congo River Lines", 1),
	("Duty Payment Receipt", "DPR/MAT/5512", -20, "Matadi Customs", 1),
	("Delivery Order", "DO/MAT/3310", -17, "Matadi Clearing Agents", 0),
]


def run():
	shipment = create_shipment()
	receipt = create_goods_receipt()
	create_landed_cost(receipt)
	link_receipt(shipment, receipt)
	create_site_receipt()


def create_shipment():
	existing = frappe.db.get_value("Shipment Tracking", {"project": _project()}, "name")
	if existing:
		log("shipment already present: %s" % existing)
		return frappe.get_doc("Shipment Tracking", existing)

	po = frappe.db.get_value("Purchase Order",
	                         {"supplier": "MBK Steel Traders", "docstatus": 1}, "name")

	doc = frappe.new_doc("Shipment Tracking")
	doc.project = _project()
	doc.cost_head = university_head()
	doc.purchase_order = po
	doc.supplier = "MBK Steel Traders"
	doc.shipment_type = "Import"
	doc.delivery_mode = "Direct to Warehouse"
	doc.status = "Received at Warehouse"
	doc.asn_no = "ASN/MBK/0041"
	doc.asn_date = day(-76)
	doc.expected_receipt_date = day(-12)
	doc.origin_port = "Shanghai"
	doc.discharge_port = "Matadi"
	doc.etd_origin = day(-70)
	doc.eta_discharge = day(-28)
	doc.ata_discharge = day(-26)
	doc.bl_no = "BL-CRL-55120"
	doc.bl_date = day(-70)
	doc.cnf_agent = "Matadi Clearing Agents"
	doc.be_no = "BE/MAT/8842"
	doc.be_date = day(-24)
	doc.duty_paid_amount = 4820
	doc.clearance_date = day(-18)
	doc.shipping_line = "Congo River Lines"
	doc.service_route = "Shanghai - Matadi"
	# Returned four days past the 14 free days, so demurrage is real.
	doc.container_return_date = day(-8)
	doc.demurrage_days = 4
	doc.demurrage_amount = 640
	doc.detention_amount = 180
	doc.transporter = "MBK Inland Haulage"
	doc.lr_no = "LR-4471"
	doc.inland_despatch_date = day(-16)
	doc.inland_arrival_date = day(-12)

	for milestone, ref, planned, actual, container, seal in MILESTONES:
		doc.append("milestones", {
			"milestone": milestone, "reference_no": ref,
			"planned_date": day(planned), "actual_date": day(actual),
			"container_type": container, "seal_no": seal,
		})
	for doc_type, number, when, issued_by, received in DOCUMENTS:
		doc.append("documents", {
			"document_type": doc_type, "document_no": number,
			"document_date": day(when), "issued_by": issued_by,
			"is_original_received": received,
			"received_date": day(when + 5) if received else None,
		})

	doc.flags.ignore_permissions = True
	doc.insert()
	log("shipment %s: transit %s days, demurrage %s" % (
		doc.name, doc.transit_days, flt(doc.demurrage_amount)))
	return doc


def create_goods_receipt():
	"""The GRN against the steel order, into the central store."""
	existing = frappe.db.get_value("Purchase Receipt",
	                               {"supplier": "MBK Steel Traders", "docstatus": 1}, "name")
	if existing:
		log("goods receipt already present: %s" % existing)
		return frappe.get_doc("Purchase Receipt", existing)

	po_name = frappe.db.get_value("Purchase Order",
	                              {"supplier": "MBK Steel Traders", "docstatus": 1}, "name")
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	doc = make_purchase_receipt(po_name)
	doc.posting_date = day(-12)
	doc.set_posting_time = 1
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("goods receipt %s: %s" % (doc.name, flt(doc.grand_total)))
	return doc


def create_landed_cost(receipt):
	"""Freight, duty and clearing spread across the received lines."""
	if frappe.db.exists("Landed Cost Voucher", {"docstatus": 1}):
		log("landed cost voucher already present")
		return

	expense = frappe.get_all("Account", filters={
		"company": company(), "is_group": 0, "root_type": "Expense"}, pluck="name")
	if not expense:
		log("no expense account for landed cost; skipped")
		return

	doc = frappe.new_doc("Landed Cost Voucher")
	doc.company = company()
	doc.posting_date = day(-11)
	doc.append("purchase_receipts", {
		"receipt_document_type": "Purchase Receipt",
		"receipt_document": receipt.name,
		"supplier": receipt.supplier,
		"grand_total": receipt.grand_total,
	})
	doc.set("items", [])
	doc.get_items_from_purchase_receipts()
	for description, amount in [("Ocean Freight", 3200), ("Customs Duty", 4820),
	                            ("Clearing and Handling", 1150),
	                            ("Inland Transport", 900)]:
		doc.append("taxes", {
			"expense_account": expense[0], "description": description, "amount": amount,
		})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("landed cost voucher %s: %s applied" % (
		doc.name, flt(sum(t.amount for t in doc.taxes))))


def link_receipt(shipment, receipt):
	if shipment and receipt and not shipment.purchase_receipt:
		shipment.db_set("purchase_receipt", receipt.name)


def create_site_receipt():
	"""A small delivery taken straight to site - the SMRN of head 38 row 5."""
	if frappe.db.exists("Purchase Receipt", {"is_site_receipt": 1}):
		log("site receipt already present")
		return

	doc = frappe.new_doc("Purchase Receipt")
	doc.supplier = "MBK Cement Works"
	doc.company = company()
	doc.posting_date = day(-9)
	doc.set_posting_time = 1
	doc.is_site_receipt = 1
	doc.site_receipt_no = "SMRN/MBK/0007"
	doc.append("items", {
		"item_code": "MBK-CEM-42", "qty": 400, "rate": 12.0,
		"warehouse": warehouse("MBK Site Store"),
		"project": _project(), "cost_head": university_head(),
		"wbs": "MBK-W-SUB", "cost_code": "MBK-CC-SUB",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("site receipt (SMRN) %s: %s" % (doc.name, flt(doc.grand_total)))
