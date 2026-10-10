# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01A: WBS nodes with a type, a place on site, a BOQ line and an owner.

The nine nodes from `masters` get their location (building / floor / zone), the
BOQ line they deliver and a responsible person. Three nodes are added so every
status has a case: WBS C (the lobby that VO-0003 will add) waits in Draft, the
roof terrace is On Hold pending a waterproofing decision, and site establishment
is Completed. Draft and On Hold nodes refuse postings, Active ones accept them.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, PEOPLE, as_user, comment, day, insert, log, project

SITE = "Mbandaka Site"
BLOCK = "Administrative Block"

# code: (building, floor, zone, BOQ cost head, BOQ line item, responsible)
DETAILS = {
	"MSS-W": (BLOCK, None, None, None, None, "pm"),
	"MSS-W-ES": (BLOCK, "Foundations to roof", "Whole block", "MSS-ES", None, "requester"),
	"MSS-W-AR": (BLOCK, None, None, None, None, "pm"),
	"MSS-W-DW": (BLOCK, "All floors", "Whole block", "MSS-AR-DW", None, "requester"),
	"MSS-W-FL": (BLOCK, "Ground and first", None, "MSS-AR-FL", None, "qs"),
	"MSS-W-FL-A": (BLOCK, "Ground floor", "Offices and corridors", "MSS-AR-FL", "FIN-POR-600", "requester"),
	"MSS-W-FL-B": (BLOCK, "First floor", "Offices and corridors", "MSS-AR-FL", "FIN-POR-600", "requester"),
	"MSS-W-PT": (BLOCK, "All floors", "Internal walls", "MSS-AR-PT", None, "requester"),
	"MSS-W-MEP": (BLOCK, "All floors", "Services risers", "MSS-MEP", None, "pm"),
}

# (code, name, parent, cost head, building, floor, zone, responsible, final status, reason)
NEW_NODES = [
	("MSS-W-FL-C", "WBS C: Lobby porcelain", "MSS-W-FL", "MSS-AR-FL", BLOCK, "Ground floor", "Entrance lobby", "qs",
	 "Draft", "Waiting for VO-0003 (lobby, +80 m²) to be approved before it opens."),
	("MSS-W-FL-T", "Roof terrace tiling", "MSS-W-FL", "MSS-AR-FL", BLOCK, "Roof", "Terrace", "requester",
	 "On Hold", "On hold until the client confirms the terrace waterproofing membrane."),
	("MSS-W-PRE", "Site establishment and setting out", "MSS-W", "MSS-ES", "Site compound", "Ground", "Compound",
	 "pm", "Completed", "Site cabins, hoarding and setting out finished and checked."),
]


def run():
	enrich_existing()
	create_status_cases()


def employee(role_key):
	first, last, *_ = PEOPLE[role_key]
	return frappe.db.get_value("Employee", {"first_name": first, "last_name": last, "company": COMPANY}, "name")


def boq_for(cost_head):
	return frappe.db.get_value(
		"BOQ", {"project": project(), "cost_head": cost_head, "docstatus": 1}, "name", order_by="revision_no desc"
	)


def boq_line(boq, item_code=None):
	filters = {"parent": boq, "parenttype": "BOQ"}
	if item_code:
		filters["item_code"] = item_code
	return frappe.db.get_value("BOQ Item", filters, "name", order_by="idx")


def enrich_existing():
	updated = 0
	for code, (building, floor, zone, head, item, person) in DETAILS.items():
		if not frappe.db.exists("WBS", code):
			continue
		doc = frappe.get_doc("WBS", code)
		values = {"location": SITE, "building": building, "floor": floor, "zone": zone,
		          "responsible_person": employee(person)}
		if head and (boq := boq_for(head)):
			values["boq"] = boq
			values["boq_item"] = boq_line(boq, item)
		changed = False
		for field, value in values.items():
			if value and not doc.get(field):  # leave what is there
				doc.set(field, value)
				changed = True
		if changed:
			with as_user("pm"):
				doc.save(ignore_permissions=True)
			updated += 1
	log(f"WBS details: location, BOQ line and owner on {updated} existing nodes")


def create_status_cases():
	for code, name, parent, head, building, floor, zone, person, status, reason in NEW_NODES:
		if frappe.db.exists("WBS", code):
			continue
		opening = "Draft" if status == "Draft" else "Active"
		with as_user("pm"):
			doc = insert({"doctype": "WBS", "wbs_code": code, "wbs_name": name, "parent_wbs": parent,
			              "cost_head": head, "project": project(), "is_group": 0, "node_type": "WBS", "status": opening,
			              "location": SITE, "building": building, "floor": floor, "zone": zone,
			              "responsible_person": employee(person)})
			if status != opening:
				doc.status = status
				doc.save(ignore_permissions=True)
		comment("WBS", code, reason, "pm", f"{day(-1)} 09:00:00")
		log(f"WBS {code} ({name}): {status}")
