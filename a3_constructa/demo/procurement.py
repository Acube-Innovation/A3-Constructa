# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo procurement: requisition, quotations, orders and a subcontract certificate."""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import company, day, log, warehouse
from a3_constructa.demo.masters import _project, university_head

# (item, wbs, cost code, qty, rate, supplier)
ORDER_LINES = [
	("MBK-CEM-42", "MBK-W-SUB", "MBK-CC-SUB", 2000, 12.0, "MBK Cement Works"),
	("MBK-REBAR-16", "MBK-W-SUB", "MBK-CC-SUB", 1500, 27.5, "MBK Steel Traders"),
	("MBK-AGG-20", "MBK-W-SUB", "MBK-CC-SUB", 800, 34.0, "MBK Cement Works"),
]


def run():
	mr = create_material_request()
	create_quotations()
	create_purchase_orders(mr)
	create_work_certificate()


def create_material_request():
	# Material Request carries the project on each line, not on the parent.
	existing = frappe.db.get_value("Material Request Item", {"project": _project()}, "parent")
	if existing:
		log("material request already present: %s" % existing)
		return frappe.get_doc("Material Request", existing)

	doc = frappe.new_doc("Material Request")
	doc.material_request_type = "Purchase"
	doc.company = company()
	doc.transaction_date = day(-70)
	doc.schedule_date = day(-30)
	for item, wbs, code, qty, _rate, _sup in ORDER_LINES:
		doc.append("items", {
			"item_code": item, "qty": qty, "schedule_date": day(-30),
			"warehouse": warehouse("MBK Central Store"),
			"project": _project(), "cost_head": university_head(),
			"wbs": wbs, "cost_code": code,
		})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("material request %s: %d lines" % (doc.name, len(doc.items)))
	return doc


def create_quotations():
	"""Three quotes for the cement, one of them recommended."""
	if frappe.db.exists("Supplier Quotation", {"supplier": "MBK Cement Works"}):
		log("supplier quotations already present")
		return

	quotes = [
		("MBK Cement Works", 12.0, "Qualified", 1, "Best price and proven delivery record"),
		("MBK Steel Traders", 12.8, "Qualified with Conditions", 0,
		 "Higher rate; conditional on revised payment terms"),
	]
	for supplier, rate, evaluation, recommended, remarks in quotes:
		doc = frappe.new_doc("Supplier Quotation")
		doc.supplier = supplier
		doc.company = company()
		doc.transaction_date = day(-60)
		doc.valid_till = day(30)
		doc.technical_evaluation_status = evaluation
		doc.technical_remarks = "Samples tested and compliant with specification."
		doc.is_recommended = recommended
		doc.recommendation_remarks = remarks
		doc.append("items", {
			"item_code": "MBK-CEM-42", "qty": 2000, "rate": rate,
			"schedule_date": day(-30),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
	log("supplier quotations: %d (1 recommended)" % len(quotes))


def create_purchase_orders(mr):
	if frappe.db.exists("Purchase Order", {"project": _project()}):
		log("purchase orders already present")
		return

	by_supplier = {}
	for item, wbs, code, qty, rate, supplier in ORDER_LINES:
		by_supplier.setdefault(supplier, []).append((item, wbs, code, qty, rate))

	for supplier, lines in by_supplier.items():
		doc = frappe.new_doc("Purchase Order")
		doc.supplier = supplier
		doc.company = company()
		doc.transaction_date = day(-55)
		doc.schedule_date = day(-20)
		doc.project = _project()
		for item, wbs, code, qty, rate in lines:
			doc.append("items", {
				"item_code": item, "qty": qty, "rate": rate,
				"schedule_date": day(-20),
				"warehouse": warehouse("MBK Central Store"),
				"project": _project(), "cost_head": university_head(),
				"wbs": wbs, "cost_code": code,
			})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		log("purchase order %s for %s: %s" % (doc.name, supplier, flt(doc.grand_total)))


def create_work_certificate():
	"""Blockwork certified for the month, with 5% retention withheld."""
	if frappe.db.exists("Work Certificate", {"project": _project()}):
		log("work certificate already present")
		return

	# The subcontract order the certificate is measured against.
	po = frappe.new_doc("Purchase Order")
	po.supplier = "MBK Blockwork Subcontractor"
	po.company = company()
	po.transaction_date = day(-50)
	po.schedule_date = day(40)
	po.project = _project()
	# Deliberately not is_subcontracted: that flag turns on ERPNext's
	# subcontracting flow, which wants a finished-good item and a Subcontracting
	# BOM - machinery a blockwork package does not need. The work is measured
	# and certified through Work Certificate instead, which is how head 30 of
	# the build sheet handles subcontract payment. The consequence is that the
	# Procurement "Subcontract POs" report stays empty in the demo.
	po.append("items", {
		"item_code": "MBK-SVC-BLOCK", "qty": 18000, "rate": 22.0,
		"schedule_date": day(40), "warehouse": warehouse("MBK Central Store"),
		"project": _project(), "cost_head": university_head(),
		"wbs": "MBK-W-SUP", "cost_code": "MBK-CC-BLK",
	})
	po.flags.ignore_permissions = True
	po.insert()
	po.submit()
	log("subcontract PO %s: %s" % (po.name, flt(po.grand_total)))

	doc = frappe.new_doc("Work Certificate")
	doc.project = _project()
	doc.cost_head = university_head()
	doc.wbs = "MBK-W-SUP"
	doc.subcontract_po = po.name
	doc.supplier = "MBK Blockwork Subcontractor"
	doc.certificate_no = "WC/MBK/001"
	doc.period_from = day(-40)
	doc.period_to = day(-10)
	doc.append("items", {
		"item_code": "MBK-SVC-BLOCK", "cost_code": "MBK-CC-BLK",
		"contracted_qty": 18000, "previous_qty": 0, "this_period_qty": 6200,
		"rate": 22.0, "retention_percent": 5,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("work certificate %s: certified %s, retention %s, net %s" % (
		doc.name, flt(doc.total_amount), flt(doc.total_retention),
		flt(doc.total_net_payable)))
