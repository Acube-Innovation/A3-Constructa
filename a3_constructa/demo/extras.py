# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Records that exist so no card in the demo opens an empty list.

Every workspace card that filters a list needs at least one matching row, or the
demo shows a blank screen on a feature that works. These are the odds and ends
the main story does not otherwise produce: shipments at other stages of their
life, a tool coming back, a tool written off, a credit note.
"""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import company, day, log, warehouse
from a3_constructa.demo.masters import _project, employee, university_head

# Shipments at the other lifecycle stages, so the Delivery & Logistics cards and
# the status tracker show a fleet in motion rather than one finished import.
SHIPMENTS = [
	{"suffix": "Direct to Site", "type": "Domestic", "mode": "Direct to Site",
	 "status": "Supplier Despatched", "supplier": "MBK Cement Works"},
	{"suffix": "In Customs", "type": "Import", "mode": "Direct to Warehouse",
	 "status": "Under Customs Clearance", "supplier": "MBK Steel Traders"},
	{"suffix": "Inland", "type": "Import", "mode": "Direct to Site",
	 "status": "In Inland Transit", "supplier": "MBK Steel Traders"},
]


def run():
	create_installation_item()
	create_extra_shipments()
	create_site_material_request()
	create_spare_issue()
	create_tool_return()
	create_tool_writeoff()
	create_credit_note()
	reimburse_employee()
	set_asset_statuses()
	backfill_serial_groups()


def backfill_serial_groups():
	"""Serials created before the item-group hook existed still have none."""
	from a3_constructa.overrides.serial_no import backfill_item_groups

	filled = backfill_item_groups()
	if filled:
		log("backfilled item group on %d serial numbers" % filled)


def create_installation_item():
	"""Head 32 puts Installation under Services; nothing else creates one."""
	if frappe.db.exists("Item", "MBK-SVC-INSTALL"):
		return
	frappe.get_doc({
		"doctype": "Item", "item_code": "MBK-SVC-INSTALL",
		"item_name": "Equipment Installation and Commissioning",
		"item_group": "Installation", "stock_uom": "Nos", "is_stock_item": 0,
		"description": "Installation and commissioning of plant on site.",
	}).insert(ignore_permissions=True)
	log("installation service item")


def create_extra_shipments():
	if frappe.db.count("Shipment Tracking") > 1:
		log("extra shipments already present")
		return

	for spec in SHIPMENTS:
		doc = frappe.new_doc("Shipment Tracking")
		doc.project = _project()
		doc.cost_head = university_head()
		doc.supplier = spec["supplier"]
		doc.shipment_type = spec["type"]
		doc.delivery_mode = spec["mode"]
		doc.status = spec["status"]
		doc.asn_no = "ASN/MBK/%s" % frappe.generate_hash(length=4).upper()
		doc.asn_date = day(-20)
		doc.expected_receipt_date = day(12)
		if spec["type"] == "Import":
			doc.origin_port = "Shanghai"
			doc.discharge_port = "Matadi"
			doc.etd_origin = day(-45)
			doc.eta_discharge = day(-5)
			doc.shipping_line = "Congo River Lines"
			doc.service_route = "Shanghai - Matadi"
			doc.cnf_agent = "Matadi Clearing Agents"
			doc.bl_no = "BL-CRL-%s" % frappe.generate_hash(length=5).upper()
			if spec["status"] == "In Inland Transit":
				doc.ata_discharge = day(-6)
				doc.transporter = "MBK Inland Haulage"
				doc.lr_no = "LR-%s" % frappe.generate_hash(length=4).upper()
				doc.inland_despatch_date = day(-3)
		doc.append("milestones", {
			"milestone": "Despatched from Supplier",
			"planned_date": day(-22), "actual_date": day(-20),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
	log("shipments at %d further stages" % len(SHIPMENTS))


def create_site_material_request():
	"""Head 43 row 6: site asking the central store for material."""
	if frappe.db.exists("Material Request", {"material_request_type": "Material Transfer",
	                                         "docstatus": 1}):
		log("site material request already present")
		return

	doc = frappe.new_doc("Material Request")
	doc.material_request_type = "Material Transfer"
	doc.company = company()
	doc.transaction_date = day(-6)
	doc.schedule_date = day(6)
	doc.append("items", {
		"item_code": "MBK-BLOCK-200", "qty": 2500, "schedule_date": day(6),
		"warehouse": warehouse("MBK Site Store"),
		"from_warehouse": warehouse("MBK Central Store"),
		"project": _project(), "cost_head": university_head(),
		"wbs": "MBK-W-SUP", "cost_code": "MBK-CC-BLK",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("site material request %s" % doc.name)


def create_spare_issue():
	"""The filter consumed on the excavator repair - head 54 row 20."""
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Material Issue",
	                                    "docstatus": 1}):
		log("spare issue already present")
		return

	doc = frappe.new_doc("Stock Entry")
	doc.company = company()
	doc.stock_entry_type = "Material Issue"
	doc.posting_date = day(-21)
	doc.set_posting_time = 1
	doc.project = _project()
	doc.append("items", {
		"item_code": "MBK-SPR-FILTER", "qty": 2,
		"s_warehouse": warehouse("MBK Central Store"),
		"project": _project(), "cost_head": university_head(),
		"wbs": "MBK-W-SUB", "cost_code": "MBK-CC-PLT",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("spare issue %s: 2 filters to the excavator repair" % doc.name)


def create_tool_return():
	"""One of the laser levels coming back in good order."""
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Tool Return", "docstatus": 1}):
		log("tool return already present")
		return

	doc = frappe.new_doc("Stock Entry")
	doc.company = company()
	doc.stock_entry_type = "Tool Return"
	doc.posting_date = day(-2)
	doc.set_posting_time = 1
	doc.project = _project()
	doc.append("items", {
		"item_code": "MBK-TOOL-LEVEL", "qty": 1,
		"s_warehouse": warehouse("MBK Tool Custody"),
		"t_warehouse": warehouse("MBK Central Store"),
		"project": _project(),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()

	# Mark it returned on the issue so Tools Outstanding drops it.
	issue = frappe.db.get_value("Tool Issue", {"docstatus": 1}, "name",
	                            order_by="creation desc")
	if issue:
		doc_issue = frappe.get_doc("Tool Issue", issue)
		for row in doc_issue.items:
			if row.item_code == "MBK-TOOL-LEVEL":
				row.db_set("returned_qty", row.qty)
				row.db_set("is_returned", 1)
				row.db_set("return_date", day(-2))
				row.db_set("condition_on_return", "Good")
		doc_issue.db_set("status", "Returned")
	log("tool return %s" % doc.name)


def create_tool_writeoff():
	"""A drill lost on site and written off - head 55 row 29."""
	if frappe.db.exists("Stock Entry", {"stock_entry_type": "Tool Write-off",
	                                    "docstatus": 1}):
		log("tool write-off already present")
		return

	doc = frappe.new_doc("Stock Entry")
	doc.company = company()
	doc.stock_entry_type = "Tool Write-off"
	doc.posting_date = day(-3)
	doc.set_posting_time = 1
	doc.project = _project()
	doc.append("items", {
		"item_code": "MBK-TOOL-DRILL", "qty": 1,
		"s_warehouse": warehouse("MBK Tool Custody"),
		"project": _project(), "cost_head": university_head(),
		"wbs": "MBK-W-SUP", "cost_code": "MBK-CC-PLT",
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()

	# Record the loss on the issue, with part of the value recovered from the
	# holder, so the Tool Loss Analysis report has a recovery figure.
	issue = frappe.db.get_value("Tool Issue", {"docstatus": 1}, "name", order_by="creation asc")
	if issue:
		doc_issue = frappe.get_doc("Tool Issue", issue)
		for row in doc_issue.items:
			if row.item_code == "MBK-TOOL-DRILL":
				row.db_set("returned_qty", max(flt(row.qty) - 1, 0))
				row.db_set("condition_on_return", "Unserviceable")
				row.db_set("recovery_amount", 150)
		doc_issue.db_set("status", "Lost")
	log("tool write-off %s: 1 drill lost, 150 recovered" % doc.name)


def create_credit_note():
	"""A small credit against the first progress claim."""
	if frappe.db.exists("Sales Invoice", {"is_return": 1, "docstatus": 1}):
		log("credit note already present")
		return

	invoice = frappe.db.get_value("Sales Invoice",
	                              {"docstatus": 1, "is_return": 0}, "name")
	if not invoice:
		return

	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

	doc = make_sales_return(invoice)
	doc.posting_date = day(-3)
	doc.set_posting_time = 1
	for row in doc.items:
		# A measured deduction, not the whole claim. The UOM is whole-number, so
		# the credit is one line at a reduced rate rather than a part quantity.
		row.qty = -1
		row.rate = round(abs(flt(row.rate)) * 0.02, 2)
		row.description = "Measured deduction against %s" % invoice
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("credit note %s: %s" % (doc.name, flt(doc.grand_total)))


def reimburse_employee():
	"""Pay the site expense claim back to the employee."""
	if frappe.db.exists("Payment Entry", {"party_type": "Employee", "docstatus": 1}):
		log("employee reimbursement already present")
		return

	claim = frappe.db.get_value("Expense Claim",
	                            {"docstatus": 1, "total_sanctioned_amount": [">", 0]}, "name")
	if not claim:
		return

	bank = frappe.get_all("Account", filters={
		"company": company(), "account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
		pluck="name")
	if not bank:
		return

	source = frappe.db.get_value("Expense Claim", claim,
	                             ["employee", "payable_account", "grand_total"], as_dict=True)

	# Built by hand rather than with get_payment_entry: that helper does not
	# resolve a party type for Expense Claim in v15 and raises before it returns.
	doc = frappe.new_doc("Payment Entry")
	doc.payment_type = "Pay"
	doc.company = company()
	doc.posting_date = day(-2)
	doc.party_type = "Employee"
	doc.party = source.employee
	doc.paid_from = bank[0]
	doc.paid_to = source.payable_account
	doc.paid_amount = flt(source.grand_total)
	doc.received_amount = flt(source.grand_total)
	doc.reference_no = "DEMO/%s" % claim
	doc.reference_date = day(-2)
	doc.append("references", {
		"reference_doctype": "Expense Claim", "reference_name": claim,
		"total_amount": flt(source.grand_total),
		"outstanding_amount": flt(source.grand_total),
		"allocated_amount": flt(source.grand_total),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("employee reimbursement %s: %s" % (doc.name, flt(source.grand_total)))


def set_asset_statuses():
	"""Put two machines into the states head 52's list views filter on.

	Set directly rather than through an Asset Movement: the movement doctype
	wants a full transfer to record, and all the demo needs is a machine sitting
	in each state so neither card opens empty.
	"""
	pairs = [("Concrete Mixer", "Out of Order"), ("Site Pickup", "Issue")]
	for asset_name, status in pairs:
		name = frappe.db.get_value("Asset", {"asset_name": asset_name}, "name")
		if name and frappe.db.get_value("Asset", name, "status") != status:
			frappe.db.set_value("Asset", name, "status", status)
	log("asset statuses: one out of order, one issued")
