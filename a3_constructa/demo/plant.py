# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo plant: the equipment fleet, a breakdown, spares and tools in custody."""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import company, day, log, warehouse
from a3_constructa.demo.masters import _project, employee

# (asset name, category, make, model, capacity, value, series)
FLEET = [
	("Excavator 20T", "Heavy Equipment", "CAT", "320D", 20, 145000, "HEQ-.####"),
	("Tower Crane", "Heavy Equipment", "Potain", "MDT 219", 10, 210000, "HEQ-.####"),
	("Concrete Mixer", "Small Machinery", "Fiori", "DB 460", 4, 38000, "SMA-.####"),
	("Site Pickup", "Vehicles", "Toyota", "Hilux", 1, 32000, "VEH-.####"),
	("Total Station", "Survey & Test Equipment", "Leica", "TS16", 0, 18500, "SUR-.####"),
]


def run():
	set_category_series()
	create_assets()
	create_spare_parts()
	create_repair()
	create_tool_issues()


def set_category_series():
	"""Head 51 row 2: number assets from their category, not one shared series."""
	for _name, category, _mk, _md, _cap, _val, series in FLEET:
		if not frappe.db.exists("Asset Category", category):
			continue
		if not frappe.db.get_value("Asset Category", category, "asset_naming_series"):
			frappe.db.set_value("Asset Category", category, "asset_naming_series", series)
	frappe.db.commit()
	log("asset categories numbered by their own series")


def create_assets():
	if frappe.db.exists("Asset", {"project": _project()}):
		log("assets already present")
		return

	operator = employee("Grace Mbuyi")
	for name, category, make, model, capacity, value, _series in FLEET:
		item_code = "MBK-AST-%s" % frappe.scrub(name).upper()[:12]
		if not frappe.db.exists("Item", item_code):
			frappe.get_doc({
				"doctype": "Item", "item_code": item_code, "item_name": name,
				"item_group": "All Item Groups", "stock_uom": "Nos",
				"is_stock_item": 0, "is_fixed_asset": 1, "asset_category": category,
			}).insert(ignore_permissions=True)

		doc = frappe.new_doc("Asset")
		doc.asset_name = name
		doc.item_code = item_code
		doc.asset_category = category
		doc.company = company()
		doc.project = _project()
		doc.custodian = operator
		doc.location = "Mbandaka Main Compound"
		doc.gross_purchase_amount = value
		doc.purchase_date = day(-300)
		doc.available_for_use_date = day(-290)
		doc.commissioning_date = day(-288)
		doc.make = make
		doc.model = model
		doc.serial_no = "SN-%s" % frappe.generate_hash(length=8).upper()
		doc.engine_no = "ENG-%s" % frappe.generate_hash(length=6).upper()
		doc.capacity = capacity
		doc.capacity_uom = "Nos"
		doc.warranty_start_date = day(-290)
		doc.warranty_expiry_date = day(75)
		doc.warranty_terms = "12 months parts and labour from commissioning."
		doc.calculate_depreciation = 0
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()
		doc.submit()
	log("fleet: %d assets, numbered per category" % len(FLEET))


def create_spare_parts():
	if frappe.db.exists("Asset Spare Part", {}):
		log("spare parts already present")
		return

	excavator = frappe.db.get_value("Asset", {"asset_name": "Excavator 20T"}, "name")
	doc = frappe.new_doc("Asset Spare Part")
	doc.asset_category = "Heavy Equipment"
	doc.asset = excavator
	doc.item_code = "MBK-SPR-FILTER"
	doc.part_no = "CAT-1R-0770"
	doc.make = "CAT"
	doc.model = "320D"
	doc.min_stock_qty = 4
	doc.reorder_qty = 8
	doc.default_warehouse = warehouse("MBK Central Store")
	doc.default_supplier = "MBK Steel Traders"
	doc.remarks = "Change every 500 operating hours."
	doc.flags.ignore_permissions = True
	doc.insert()
	log("spare part registered against %s" % excavator)


def create_repair():
	"""A breakdown with spares consumed, so the maintenance reports have data."""
	if frappe.db.exists("Asset Repair", {}):
		log("asset repair already present")
		return

	excavator = frappe.db.get_value("Asset", {"asset_name": "Excavator 20T"}, "name")
	doc = frappe.new_doc("Asset Repair")
	doc.asset = excavator
	doc.company = company()
	doc.failure_date = day(-22)
	doc.completion_date = day(-20)
	doc.repair_status = "Completed"
	doc.description = "Hydraulic pressure loss; filter and seals replaced."
	doc.repair_cost = 1450
	doc.project = _project()
	doc.downtime = "48 hours"
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	log("asset repair %s: %s over 2 days" % (doc.name, flt(doc.repair_cost)))


def create_tool_issues():
	"""Two tools out with the site engineer, one of them overdue."""
	if frappe.db.exists("Tool Issue", {"project": _project()}):
		log("tool issues already present")
		return

	engineer = employee("Jean Mukendi")
	surveyor = employee("Alice Kabeya")

	for holder, item, qty, due_in, label in [
		(engineer, "MBK-TOOL-DRILL", 2, -6, "overdue"),
		(surveyor, "MBK-TOOL-LEVEL", 1, 21, "in date"),
	]:
		doc = frappe.new_doc("Tool Issue")
		doc.issue_date = day(-25)
		doc.project = _project()
		doc.site = "Mbandaka Main Compound"
		doc.from_warehouse = warehouse("MBK Central Store")
		doc.to_warehouse = warehouse("MBK Tool Custody")
		doc.issued_to = holder
		doc.expected_return_date = day(due_in)
		doc.append("items", {
			"item_code": item, "qty": qty, "condition_on_issue": "Good",
			"expected_return_date": day(due_in),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		log("tool issue %s to %s (%s)" % (doc.name, holder, label))
