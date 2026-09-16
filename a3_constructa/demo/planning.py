# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo planning: the BOQ, the budget allocated to WBS, and the buying plan."""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import day, ensure_by, log
from a3_constructa.demo.masters import _project, university_head

# (item, wbs, cost code, qty, rate, approved qty, approved rate)
BOQ_LINES = [
	("MBK-CEM-42", "MBK-W-SUB", "MBK-CC-SUB", 4000, 12.0, 3800, 12.0),
	("MBK-REBAR-16", "MBK-W-SUB", "MBK-CC-SUB", 2500, 28.0, 2500, 27.5),
	("MBK-BLOCK-200", "MBK-W-SUP", "MBK-CC-BLK", 18000, 1.6, 18000, 1.6),
	("MBK-AGG-20", "MBK-W-SUB", "MBK-CC-SUB", 1200, 34.0, 1200, 34.0),
	("MBK-SCAF-SET", "MBK-W-TMP", "MBK-CC-TMP", 40, 210.0, 36, 210.0),
	("MBK-RENT-CRANE", "MBK-W-SUP", "MBK-CC-PLT", 60, 780.0, 55, 780.0),
]


def run():
	boq = create_boq()
	create_wbs_allocation(boq)
	create_procurement_plan()


def create_boq():
	existing = frappe.db.get_value("BOQ", {"project": _project()}, "name")
	if existing:
		log("BOQ already present: %s" % existing)
		return frappe.get_doc("BOQ", existing)

	doc = frappe.new_doc("BOQ")
	doc.project = _project()
	doc.cost_head = university_head()
	doc.boq_date = day(-100)
	doc.revision_no = 1
	doc.currency = frappe.db.get_value("Company", doc.company if doc.get("company") else
	                                   frappe.defaults.get_defaults().get("company"),
	                                   "default_currency")
	for item, wbs, code, qty, rate, appr_qty, appr_rate in BOQ_LINES:
		doc.append("items", {
			"item_code": item, "wbs": wbs, "cost_code": code, "uom": "Nos",
			"boq_qty": qty, "rate": rate,
			"approved_qty": appr_qty, "approved_rate": appr_rate,
		})
	doc.flags.ignore_permissions = True
	doc.insert()

	# Everything downstream needs an approved BOQ, and the BOQ Approval workflow
	# will not allow a jump straight to Approved - which is the point of it. So
	# the demo walks the same path a quantity surveyor and an approver would.
	from frappe.model.workflow import apply_workflow

	apply_workflow(doc, "Submit for Approval")
	apply_workflow(doc, "Approve")
	doc.reload()

	log("BOQ %s: %d lines, total %s, status %s" % (
		doc.name, len(doc.items), flt(doc.total_amount), doc.status))
	return doc


def create_wbs_allocation(boq):
	existing = frappe.db.get_value("WBS Allocation", {"boq": boq.name}, "name")
	if existing:
		log("WBS allocation already present: %s" % existing)
		return

	# One allocation per WBS node, so the Budget vs WBS report has something to
	# group by.
	for wbs in ("MBK-W-SUB", "MBK-W-SUP", "MBK-W-TMP"):
		lines = [r for r in boq.items if r.wbs == wbs]
		if not lines:
			continue
		doc = frappe.new_doc("WBS Allocation")
		doc.project = _project()
		doc.boq = boq.name
		doc.wbs = wbs
		doc.cost_head = university_head()
		for row in lines:
			doc.append("items", {
				"boq_item": row.name, "item_code": row.item_code,
				"cost_code": row.cost_code,
				# Allocate the approved quantity - that is what was signed off.
				"allocated_qty": flt(row.approved_qty), "rate": flt(row.approved_rate),
			})
		doc.flags.ignore_permissions = True
		doc.insert()
		log("WBS allocation %s for %s: %s" % (
			doc.name, wbs, flt(sum(r.allocated_amount for r in doc.items))))


def create_procurement_plan():
	existing = frappe.db.get_value("Procurement Plan", {"project": _project()}, "name")
	if existing:
		log("procurement plan already present: %s" % existing)
		return

	doc = frappe.new_doc("Procurement Plan")
	doc.project = _project()
	doc.cost_head = university_head()
	doc.plan_date = day(-90)
	doc.status = "Submitted"
	# Required-on-site dates run forward from today so the recommended PR dates
	# are a mix of overdue and still to come.
	for item, wbs, code, qty, required_in in [
		("MBK-CEM-42", "MBK-W-SUB", "MBK-CC-SUB", 3800, 14),
		("MBK-REBAR-16", "MBK-W-SUB", "MBK-CC-SUB", 2500, 21),
		("MBK-BLOCK-200", "MBK-W-SUP", "MBK-CC-BLK", 18000, 45),
		("MBK-AGG-20", "MBK-W-SUB", "MBK-CC-SUB", 1200, 10),
	]:
		doc.append("items", {
			"item_code": item, "wbs": wbs, "cost_code": code,
			"boq_qty": qty, "anticipated_qty": qty, "uom": "Nos",
			"required_on_site_date": day(required_in),
			"remarks": "From approved BOQ",
		})
	doc.flags.ignore_permissions = True
	doc.insert()
	log("procurement plan %s: %d lines" % (doc.name, len(doc.items)))
