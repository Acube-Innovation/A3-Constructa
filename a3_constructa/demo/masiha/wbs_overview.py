# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-01: give the WBS & Cost Structure Overview something to flag.

- Mezzanine tiling (MSS-W-FL-D) was opened and a request raised for it, then
  the client paused the mezzanine: the node is On Hold with that draft request
  still booked to it.
- External paving (MSS-W-EXT) is set up in Draft with nobody responsible yet.
- Scaffold hire under the old supplier (MSS-CC-SCF) was deactivated while a
  draft order still used it.
- A budget transfer this month, so "budget changes this month" has a figure.

The overspent-allowance check stays clear: the BOQ refuses an overspent
allowance on save.
"""

import frappe
from frappe.utils import getdate

from a3_constructa.demo.masiha.common import (
	COMPANY, acc, as_user, at, comment, cost_center, day, insert, log, project, wh,
)

MEZZANINE = "MSS-W-FL-D"
PAVING = "MSS-W-EXT"
SCAFFOLD = "MSS-CC-SCF"


def run():
	made = [mezzanine_on_hold(), paving_without_owner(), scaffold_code_closed(), transfer_this_month()]
	log("WBS overview cases: " + ", ".join(m for m in made if m))


def employee(first, last):
	return frappe.db.get_value("Employee", {"first_name": first, "last_name": last, "company": COMPANY}, "name")


def mezzanine_on_hold():
	if frappe.db.exists("WBS", MEZZANINE):
		return None
	with as_user("pm"):
		node = insert({"doctype": "WBS", "wbs_code": MEZZANINE, "wbs_name": "Mezzanine tiling", "parent_wbs": "MSS-W-FL",
		               "cost_head": "MSS-AR-FL", "project": project(), "node_type": "WBS", "status": "Active",
		               "location": "Mbandaka Site", "building": "Administrative Block", "floor": "Mezzanine",
		               "zone": "Meeting rooms", "responsible_person": employee("Esther", "Ngalula")})
	with as_user("requester"):
		mr = insert({"doctype": "Material Request", "material_request_type": "Purchase", "company": COMPANY,
		             "transaction_date": day(-14), "schedule_date": day(7),
		             "items": [{"item_code": "FIN-POR-600", "qty": 90, "rate": 18.50, "schedule_date": getdate(day(7)),
		                        "warehouse": wh("Mbandaka Site Store"), "project": project(), "wbs": MEZZANINE,
		                        "cost_code": "MSS-CC-FIN-M"}]})
	frappe.db.set_value("Material Request", mr.name, "creation", at(-14, 9), update_modified=False)
	with as_user("pm"):
		node.reload()
		node.status = "On Hold"
		node.save(ignore_permissions=True)
	comment("WBS", MEZZANINE, "On hold: the client is reviewing the mezzanine layout. Request "
	        f"{mr.name} is waiting on it.", "pm", at(-9, 10))
	return f"{MEZZANINE} On Hold with draft {mr.name}"


def paving_without_owner():
	if frappe.db.exists("WBS", PAVING):
		return None
	with as_user("pm"):
		insert({"doctype": "WBS", "wbs_code": PAVING, "wbs_name": "External paving and drainage", "parent_wbs": "MSS-W",
		        "cost_head": "MSS-ES", "project": project(), "node_type": "WBS", "status": "Draft",
		        "location": "Mbandaka Site", "building": "Site compound", "zone": "Forecourt"})
	# Frappe fills an Employee link with the creating user's own employee; this
	# node is the one still waiting for someone to be named.
	frappe.db.set_value("WBS", PAVING, {"responsible_person": None, "responsible_person_name": None}, update_modified=False)
	return f"{PAVING} Draft, no responsible person"


def scaffold_code_closed():
	if frappe.db.exists("Cost Code", SCAFFOLD):
		return None
	insert({"doctype": "Cost Code", "cost_code": SCAFFOLD, "category": "Rental", "status": "Active",
	        "description": "Scaffold hire - Kinshasa Echafaudages (contract ended)",
	        "account": acc("Plant and Equipment Costs"), "cost_center": cost_center()})
	with as_user("buyer"):
		po = insert({"doctype": "Purchase Order", "company": COMPANY, "supplier": "Kinshasa Building Supplies SARL",
		             "transaction_date": day(-8), "schedule_date": day(10), "project": project(),
		             "items": [{"item_code": "SVC-TILE-INST", "description": "Scaffold hire, 4 weeks, stair core",
		                        "qty": 1, "uom": frappe.db.get_value("Item", "SVC-TILE-INST", "stock_uom"), "rate": 1450,
		                        "schedule_date": getdate(day(10)), "project": project(), "wbs": "MSS-W-ES", "cost_code": SCAFFOLD}]})
	code = frappe.get_doc("Cost Code", SCAFFOLD)
	code.status = "Inactive"
	code.save(ignore_permissions=True)
	comment("Purchase Order", po.name, "Scaffold contract with this supplier has ended; rebook to the new framework cost code before approval.",
	        "procurement", at(-3, 11))
	return f"{SCAFFOLD} Inactive, still on draft {po.name}"


def transfer_this_month():
	month_start = getdate(day(0)).replace(day=1)
	if frappe.db.exists("Budget Revision Log", {"project": project(), "posted_on": [">=", month_start], "change_type": "Transfer In"}):
		return None
	when = max(month_start, getdate(day(-2)))
	with as_user("qs"):
		bt = insert({"doctype": "Budget Transfer", "project": project(), "transfer_date": when,
		             "reason": "Heavy-duty door closers for the public entrances, paid from MEP cable savings.",
		             "items": [{"from_wbs": "MSS-W-MEP", "from_cost_code": "MSS-CC-MEP-M", "to_wbs": "MSS-W-DW",
		                        "to_cost_code": "MSS-CC-DW-M", "amount": 400}]})
	with as_user("pm"):
		bt.submit()
	for row in frappe.get_all("Budget Revision Log", filters={"reference_name": bt.name}, pluck="name"):
		frappe.db.set_value("Budget Revision Log", row, "posted_on", f"{when} 15:00:00", update_modified=False)
	return f"{bt.name} this month"
