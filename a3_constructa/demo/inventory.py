# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo inventory: opening stock, issues to the job, a transit leg and a return."""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import company, day, log, warehouse
from a3_constructa.demo.masters import _project, university_head

# Stock the central store starts with, beyond what the purchase orders brought.
OPENING = [
	("MBK-CEM-42", 3000, 12.0),
	("MBK-BLOCK-200", 9000, 1.6),
	("MBK-AGG-20", 900, 34.0),
	("MBK-SCAF-SET", 36, 210.0),
	("MBK-TOOL-DRILL", 6, 380.0),
	("MBK-TOOL-LEVEL", 3, 640.0),
	("MBK-SPR-FILTER", 12, 95.0),
]

# What has been issued to the job so far, against WBS and cost code.
ISSUES = [
	("MBK-CEM-42", 1450, "MBK-W-SUB", "MBK-CC-SUB", -35),
	# Rebar only lands with the import goods receipt on day -12, so it cannot
	# be issued before then.
	("MBK-REBAR-16", 820, "MBK-W-SUB", "MBK-CC-SUB", -10),
	("MBK-AGG-20", 460, "MBK-W-SUB", "MBK-CC-SUB", -21),
	("MBK-BLOCK-200", 5400, "MBK-W-SUP", "MBK-CC-BLK", -14),
	("MBK-SCAF-SET", 22, "MBK-W-TMP", "MBK-CC-TMP", -30),
]


def run():
	create_opening_stock()
	create_issues()
	create_transit_leg()
	create_site_return()


def create_opening_stock():
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Material Receipt",
	                                    "docstatus": 1}):
		log("opening stock already present")
		return

	doc = frappe.new_doc("Stock Entry")
	doc.company = company()
	doc.stock_entry_type = "Material Receipt"
	doc.posting_date = day(-60)
	doc.set_posting_time = 1
	for item, qty, rate in OPENING:
		doc.append("items", {
			"item_code": item, "qty": qty, "basic_rate": rate,
			"t_warehouse": warehouse("MBK Central Store"),
		})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("opening stock %s: %d items" % (doc.name, len(doc.items)))


def create_issues():
	"""Material issue notes, each tagged to the WBS and cost code it was used on."""
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Material Issue Note (MIN)",
	                                    "docstatus": 1}):
		log("material issues already present")
		return

	for item, qty, wbs, code, when in ISSUES:
		doc = frappe.new_doc("Stock Entry")
		doc.company = company()
		doc.stock_entry_type = "Material Issue Note (MIN)"
		doc.posting_date = day(when)
		doc.set_posting_time = 1
		doc.project = _project()
		doc.append("items", {
			"item_code": item, "qty": qty,
			"s_warehouse": warehouse("MBK Central Store"),
			"project": _project(), "cost_head": university_head(),
			"wbs": wbs, "cost_code": code,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
	log("material issues: %d, each against a WBS and cost code" % len(ISSUES))


def create_transit_leg():
	"""Central store to site via the transit warehouse - head 44 of the sheet."""
	if frappe.db.exists("Stock Entry", {"add_to_transit": 1, "docstatus": 1}):
		log("transit leg already present")
		return

	out = frappe.new_doc("Stock Entry")
	out.company = company()
	out.stock_entry_type = "Material Transfer"
	out.add_to_transit = 1
	out.posting_date = day(-18)
	out.set_posting_time = 1
	out.project = _project()
	out.mode_of_transport = "Barge"
	out.transporter = "MBK Inland Haulage"
	out.vehicle_no = "BRG-114"
	out.lr_no = "LR-4502"
	out.append("items", {
		"item_code": "MBK-CEM-42", "qty": 600,
		"s_warehouse": warehouse("MBK Central Store"),
		"t_warehouse": warehouse("MBK Transit"),
		"project": _project(), "wbs": "MBK-W-SUB", "cost_code": "MBK-CC-SUB",
	})
	out.flags.ignore_permissions = True
	out.insert()
	out.submit()
	log("sent to transit %s: 600 bags by barge" % out.name)

	# The receiving leg - the MRN of head 46. Part of the load is still afloat,
	# so only 450 of the 600 are received and the rest shows as in-transit stock.
	mrn = frappe.new_doc("Stock Entry")
	mrn.company = company()
	mrn.stock_entry_type = "Material Receipt Note (MRN)"
	mrn.posting_date = day(-11)
	mrn.set_posting_time = 1
	mrn.project = _project()
	mrn.append("items", {
		"item_code": "MBK-CEM-42", "qty": 450,
		"s_warehouse": warehouse("MBK Transit"),
		"t_warehouse": warehouse("MBK Site Store"),
		"project": _project(), "wbs": "MBK-W-SUB", "cost_code": "MBK-CC-SUB",
	})
	mrn.flags.ignore_permissions = True
	mrn.insert()
	mrn.submit()
	log("received at site %s: 450 bags, 150 still in transit" % mrn.name)


def create_site_return():
	"""Surplus material coming back off site."""
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Site Material Return",
	                                    "docstatus": 1}):
		log("site return already present")
		return

	doc = frappe.new_doc("Stock Entry")
	doc.company = company()
	doc.stock_entry_type = "Site Material Return"
	doc.posting_date = day(-5)
	doc.set_posting_time = 1
	doc.project = _project()
	# Surplus cement going back to store. Scaffolding was issued rather than
	# transferred, so none of it sits at the site warehouse to return.
	doc.append("items", {
		"item_code": "MBK-CEM-42", "qty": 60,
		"s_warehouse": warehouse("MBK Site Store"),
		"t_warehouse": warehouse("MBK Central Store"),
		"project": _project(), "wbs": "MBK-W-SUB", "cost_code": "MBK-CC-SUB",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("site return %s: 60 surplus bags back to store" % doc.name)
