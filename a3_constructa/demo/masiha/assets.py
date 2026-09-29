# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Step 19: the excavator, from receipt to a depreciating asset working on site."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from frappe.utils import get_last_day

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, exists, log, project

SUPPLIER = "Equipements Lourds du Congo SARL"


def run():
	receipt = receive()
	asset = register(receipt)
	move_to_site(asset)
	depreciate()
	frappe.db.commit()


def receive():
	existing = frappe.db.get_value("Purchase Receipt", {"supplier": SUPPLIER, "company": COMPANY, "docstatus": 1}, "name")
	if existing:
		return existing
	po = frappe.db.get_value("Purchase Order", {"supplier": SUPPLIER, "company": COMPANY, "docstatus": 1}, "name")
	pr = make_purchase_receipt(po)
	pr.posting_date = day(-62)
	pr.set_posting_time = 1
	for row in pr.items:
		row.asset_location = "Kinshasa Central Yard"
		row.cost_head, row.wbs, row.cost_code = "MSS-ES", "MSS-W-ES", "MSS-CC-PLT"
	with as_user("stores"):
		pr.insert()
		pr.submit()
	log(f"equipment receipt {pr.name}: the asset record is created from it")
	return pr.name


def register(receipt):
	name = frappe.db.get_value("Asset", {"purchase_receipt": receipt}, "name")
	asset = frappe.get_doc("Asset", name)
	if asset.docstatus == 1:
		return name
	operator = frappe.db.get_value("Employee", {"first_name": "Joseph", "last_name": "Mbala", "company": COMPANY}, "name")
	asset.update({
		"make": "Liugong", "model": "922F", "serial_no": "LG922F-26-004471", "engine_no": "CUMMINS-QSB67-88230",
		"chassis_no": "LGCH922F0026447", "capacity": 20, "capacity_uom": "Tonne", "custodian": operator,
		"location": "Kinshasa Central Yard", "project": project(), "available_for_use_date": day(-60),
		"commissioning_date": day(-60), "warranty_start_date": day(-60), "warranty_expiry_date": day(305),
		"warranty_terms": "12 months or 2,000 engine hours, parts and labour.", "calculate_depreciation": 1,
	})
	asset.set("finance_books", [{"depreciation_method": "Straight Line", "total_number_of_depreciations": 60,
	                             "frequency_of_depreciation": 1, "depreciation_start_date": get_last_day(day(-60))}])
	with as_user("finance"):
		asset.save()
		asset.submit()
	comment("Asset", name, "Commissioned at Kinshasa Central Yard; capitalised at cost on receipt. "
	        "Depreciation straight line over 60 months.", "finance", at(-60, 15))
	log(f"asset {name}: serial, engine and chassis recorded, custodian Joseph Mbala, capitalised")
	return name


def move_to_site(asset):
	if exists("Asset Movement", {"company": COMPANY, "docstatus": 1}):
		return
	operator = frappe.db.get_value("Asset", asset, "custodian")
	movement = frappe.get_doc({"doctype": "Asset Movement", "company": COMPANY, "purpose": "Transfer",
	                           "transaction_date": f"{day(-45)} 08:00:00",
	                           "assets": [{"asset": asset, "source_location": "Kinshasa Central Yard",
	                                       "target_location": "Mbandaka Site", "to_employee": operator}]})
	with as_user("finance"):
		movement.insert()
		movement.submit()
	log(f"asset movement {movement.name}: excavator transferred to Mbandaka site")


def depreciate():
	from erpnext.assets.doctype.asset.depreciation import post_depreciation_entries

	post_depreciation_entries(date=day(0))
	count = frappe.db.count("Journal Entry", {"company": COMPANY, "voucher_type": "Depreciation Entry", "docstatus": 1})
	log(f"depreciation: {count} monthly entries posted to date")
