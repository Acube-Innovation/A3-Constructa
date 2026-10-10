# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01B: allowance lines and the 100% rule.

An Architectural provisional-sums BOQ carries two allowances: a $12,000 PC sum
for the lobby feature wall, part of which is already spent on 120 m² of feature
porcelain drawn from it, and a $5,000 dayworks provisional sum. Four
allocations split it across the works, one in each state: submitted, draft,
cancelled, and the amendment that replaced the cancelled one. What is left
shows in Unallocated BOQ Lines and as the Unallocated row of Budget vs WBS.
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, at, comment, day, insert, log, project
from a3_constructa.demo.masiha.planning import _approve

HEAD = "MSS-AR"
FEATURE_WALL = "PC sum: lobby feature wall cladding"
DAYWORKS = "Provisional sum: dayworks"


def run():
	boq = create_boq()
	create_allocations(boq)


def create_boq():
	existing = frappe.db.get_value("BOQ", {"project": project(), "cost_head": HEAD, "docstatus": 1}, "name")
	if existing:
		log(f"provisional-sums BOQ already present: {existing}")
		return frappe.get_doc("BOQ", existing)

	with as_user("qs"):
		boq = insert({
			"doctype": "BOQ", "project": project(), "cost_head": HEAD, "boq_date": day(-60), "currency": "USD",
			"items": [
				{"is_allowance": 1, "description": FEATURE_WALL, "wbs": "MSS-W-AR", "cost_code": "MSS-CC-FIN-M",
				 "amount": 12000},
				{"item_code": "FIN-POR-600", "description": "Feature porcelain 600 x 600 mm R10, lobby wall",
				 "wbs": "MSS-W-AR", "cost_code": "MSS-CC-FIN-M", "boq_qty": 120, "rate": 20.00,
				 "approved_qty": 120, "approved_rate": 18.50},
				{"is_allowance": 1, "description": DAYWORKS, "wbs": "MSS-W-AR", "cost_code": "MSS-CC-FIN-S",
				 "amount": 5000},
				{"item_code": "FIN-ADH-C2", "wbs": "MSS-W-AR", "cost_code": "MSS-CC-FIN-M", "boq_qty": 30,
				 "rate": 10.50, "approved_qty": 30, "approved_rate": 9.80},
			],
		})
		# The feature porcelain is paid out of the PC sum, not on top of it.
		boq.items[1].draws_from_allowance = boq.items[0].name
		boq.save(ignore_permissions=True)
	boq = _approve(boq, -59, "Provisional sums approved: PC sum $12,000 (feature porcelain $2,220 drawn from it), dayworks $5,000.")
	log(f"BOQ {boq.name}: PC sum $12,000 with $2,220 drawn, dayworks $5,000, adhesive 30 bags")
	return boq


def create_allocations(boq):
	if frappe.db.exists("WBS Allocation", {"boq": boq.name}):
		log("provisional-sum allocations already present")
		return
	line = {row.idx: row for row in boq.items}

	def allocate(wbs, rows, by="qs"):
		with as_user(by):
			return insert({
				"doctype": "WBS Allocation", "project": project(), "boq": boq.name, "wbs": wbs, "cost_head": HEAD,
				"items": rows,
			})

	def qty_row(idx, qty):
		return {"boq_item": line[idx].name, "item_code": line[idx].item_code, "cost_code": line[idx].cost_code,
		        "allocated_qty": qty, "rate": line[idx].approved_rate}

	def amount_row(idx, amount):
		return {"boq_item": line[idx].name, "cost_code": line[idx].cost_code, "allocated_amount": amount}

	# Submitted: the feature wall goes on the ground floor, with $4,000 of the PC sum.
	a1 = allocate("MSS-W-FL-A", [qty_row(2, 120), amount_row(1, 4000)])
	with as_user("pm"):
		a1.submit()
	comment("WBS Allocation", a1.name, "Lobby feature wall on WBS A: all 120 m² of feature porcelain and $4,000 of the PC sum.", "qs", at(-58, 10))

	# Draft: first-floor dayworks and adhesive, still being checked.
	a2 = allocate("MSS-W-FL-B", [amount_row(3, 1500), qty_row(4, 20)])
	comment("WBS Allocation", a2.name, "Draft until the first-floor daywork sheets are agreed.", "qs", at(-50, 15))

	# Cancelled and amended: 10 bags booked to painting, corrected to 8.
	a3 = allocate("MSS-W-PT", [qty_row(4, 10)])
	with as_user("pm"):
		a3.submit()
		a3.reload()
		a3.cancel()
		amended = frappe.copy_doc(a3)
		amended.amended_from = a3.name
		amended.items[0].allocated_qty = 8
		amended.flags.ignore_permissions = True
		amended.insert()
		amended.submit()
	comment("WBS Allocation", amended.name, "Corrected from 10 to 8 bags after the painting take-off.", "pm", at(-45, 11))

	log(f"allocations: {a1.name} submitted, {a2.name} draft, {a3.name} cancelled -> {amended.name} submitted")
