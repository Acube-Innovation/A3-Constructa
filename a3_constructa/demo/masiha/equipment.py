# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-08A: the plant's days, logged and charged.

- The 20 t excavator (owned, HEQ-0001) is charged at an internal $85 a worked hour
  to Equipment cost code MSS-CC-EQP. It dug the Administrative Centre's
  foundations for a week (a rain day mostly idle, a hydraulic hose cost three
  hours), then a day at the hospital; today's log waits for the evening reading.
- A 25 t mobile crane is hired from Equipements Lourds du Congo for the hospital
  frame at $650 a day; its logs carry hours only, and the supplier has invoiced
  the first three days against the hire order.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, acc, as_user, at, comment, day, insert, log, project

EXCAVATOR = "HEQ-0001"
COST_CODE = "MSS-CC-EQP"
HOSPITAL_SITE = "Mbandaka Hospital Site"
CRANE_ITEM, CRANE_HIRE = "EQ-CRANE-25T", "EQ-CRANE-HIRE"
HIRER = "Equipements Lourds du Congo SARL"
# day, project key, meter start, meter end, worked, idle, breakdown, remarks
EXCAVATOR_DAYS = [
	(-12, "admin", 1240, 1247.5, 7.5, 0.5, 0, "Bulk dig, grid lines A-C"),
	(-11, "admin", 1247.5, 1255, 7.5, 0, 0, "Bulk dig, grid lines C-F"),
	(-10, "admin", 1255, 1257, 2, 6, 0, "Rain from 09:00; stood by"),
	(-9, "admin", 1257, 1262, 5, 0, 3, "Hydraulic hose burst at 13:00; fitter from Kinshasa Central Yard"),
	(-8, "admin", 1262, 1270, 8, 0, 0, "Pad foundations, gridline F"),
	(-5, "hospital", 1270, 1276.5, 6.5, 1.5, 0, "Lift pit excavation at the hospital"),
]
CRANE_DAYS = [(-7, 0, 6, 6, 2, 0, "Rebar cages, level 1"), (-6, 6, 14, 8, 0, 0, "Precast stair flights"),
              (-4, 14, 17, 3, 5, 0, "Waiting for the steel delivery")]


def run():
	if frappe.db.exists("Equipment Log", {"asset": EXCAVATOR}):
		log("equipment logs already present")
		return
	sites = setup()
	operator = operator_employee()
	excavator_logs = [equipment_log(EXCAVATOR, d, sites[p], *rest, operator=operator) for d, p, *rest in EXCAVATOR_DAYS]
	draft = equipment_log(EXCAVATOR, 0, sites["admin"], 1276.5, 0, 0, 0, 0, "Backfill to pads, gridline F", operator=operator, submit=False)
	crane, po = hired_crane(sites)
	crane_logs = [equipment_log(crane, d, sites["hospital"], *rest) for d, *rest in CRANE_DAYS]
	pi = hire_invoice(po)
	log(f"Excavator: {len(excavator_logs)} logs charged, {draft} draft; crane {crane} (hired on {po}): {len(crane_logs)} logs, invoice {pi}")


def setup():
	if not frappe.db.exists("Cost Code", COST_CODE):
		insert({"doctype": "Cost Code", "cost_code": COST_CODE, "description": "Owned plant - internal hire", "category": "Equipment",
		        "account": acc("Plant and Equipment Costs"), "cost_center": acc("Main"), "status": "Active"})
	if not frappe.db.exists("Location", HOSPITAL_SITE):
		insert({"doctype": "Location", "location_name": HOSPITAL_SITE})
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")
	frappe.db.set_value("Asset", EXCAVATOR, {"internal_hourly_rate": 85, "meter_type": "Hours", "current_meter": 1240, "project": project(),
	                                         "wbs": "MSS-W-ES", "cost_code": COST_CODE})
	comment("Asset", EXCAVATOR, "Internal hire rate set at $85 per worked hour (depreciation, fuel, maintenance, operator).", "pm", at(-13, 9))
	return {"admin": (project(), "Mbandaka Site", "MSS-W-ES"), "hospital": (hospital, HOSPITAL_SITE, "HGR-W-ES")}


def operator_employee():
	name = frappe.db.get_value("Employee", {"first_name": "Patrice", "last_name": "Ekofo", "company": COMPANY}, "name")
	if name:
		return name
	if not frappe.db.exists("Designation", "Plant Operator"):
		insert({"doctype": "Designation", "designation_name": "Plant Operator"})
	return insert({"doctype": "Employee", "first_name": "Patrice", "last_name": "Ekofo", "gender": "Male", "company": COMPANY,
	               "date_of_birth": "1987-06-12", "date_of_joining": day(-300), "status": "Active", "designation": "Plant Operator"}).name


def equipment_log(asset, when, site, meter_start, meter_end, worked, idle, breakdown, remarks, operator=None, submit=True):
	project_name, location, wbs = site
	with as_user("requester"):
		d = frappe.get_doc({"doctype": "Equipment Log", "asset": asset, "log_date": day(when), "project": project_name, "site": location,
		                    "wbs": wbs, "operator": operator, "meter_start": meter_start, "meter_end": meter_end, "worked_hours": worked,
		                    "idle_hours": idle, "breakdown_hours": breakdown, "remarks": remarks})
		d.flags.ignore_permissions = True
		d.insert()
		if submit:
			d.submit()
	frappe.db.set_value("Equipment Log", d.name, {"creation": at(when, 17), "modified": at(when, 17, 30)}, update_modified=False)
	return d.name


def hired_crane(sites):
	for code, name, fixed in ((CRANE_ITEM, "Mobile crane 25 t", 1), (CRANE_HIRE, "Mobile crane 25 t hire, with operator, per day", 0)):
		if not frappe.db.exists("Item", code):
			insert({"doctype": "Item", "item_code": code, "item_name": name, "item_group": "Heavy Equipment Items" if fixed else "Services",
			        "stock_uom": "Nos" if fixed else "Day", "is_stock_item": 0, "is_fixed_asset": fixed,
			        "asset_category": "Heavy Equipment" if fixed else None, "include_item_in_manufacturing": 0})
	from a3_constructa.demo.masiha.ledger import _order

	po = _order(HIRER, CRANE_HIRE, 10, 650, "HGR-W-ES", "MSS-CC-PLT", -9)
	frappe.db.set_value("Purchase Order", po.name, "project", sites["hospital"][0])
	frappe.db.sql("update `tabPurchase Order Item` set project = %s where parent = %s", (sites["hospital"][0], po.name))
	with as_user("pm"):
		a = frappe.get_doc({"doctype": "Asset", "asset_name": "Mobile crane 25 t (hired)", "item_code": CRANE_ITEM, "company": COMPANY,
		                    "asset_category": "Heavy Equipment", "location": HOSPITAL_SITE, "is_existing_asset": 1,
		                    "available_for_use_date": day(-8), "purchase_date": day(-8), "calculate_depreciation": 0,
		                    # ERPNext wants a value even on a draft: the hirer's declared value, for insurance.
		                    "gross_purchase_amount": 280_000,
		                    "is_hired": 1, "hire_purchase_order": po.name, "meter_type": "Hours", "project": sites["hospital"][0],
		                    "wbs": "HGR-W-ES", "make": "Liebherr", "model": "LTM 1030-2.1"})
		a.flags.ignore_permissions = True
		a.insert()
	comment("Asset", a.name, "Hired with operator for the hospital frame: 10 days on PO " + po.name + ". Not our asset: kept as a draft (at the hirer's declared value of $280,000) so its days can be logged.", "pm", at(-8, 8))
	return a.name, po.name


def hire_invoice(po):
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

	pi = make_purchase_invoice(po)
	for row in pi.items:
		row.qty = 3
	pi.update({"posting_date": day(-3), "set_posting_time": 1, "bill_no": "ELC-2026-0918", "bill_date": day(-3), "due_date": None})
	pi.payment_schedule = []
	pi.flags.silent_three_way = True
	with as_user("finance"):
		pi.flags.ignore_permissions = True
		pi.insert()
		pi.submit()
	return pi.name
