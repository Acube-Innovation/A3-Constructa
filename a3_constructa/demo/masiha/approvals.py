# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-09A: approval levels and the budget check on requests and orders.

Seven documents, one for each place an approval can be:

- MR adhesive (under $10,000): one level, the project manager; approved, which
  also takes the workflow's approving step, so it is submitted.
- MR cement (about $22,000): two levels; the project manager has approved,
  the procurement manager has not yet.
- MR paint: rejected by the project manager (wrong WBS).
- PO rebar (about $31,000): two levels; procurement approved, waiting for the
  A3 Constructa Admin level.
- PO grout: raised six days ago, nobody has approved it yet (overdue).
- PO paint: approved and submitted over the painting budget; the budget check
  warned and named the overrun.
- PO spacers: approved and submitted, then cancelled (supplier out of stock)
  and amended as -1 for fewer bags, waiting for approval again.
"""

import frappe
from frappe.utils import add_days, getdate, now_datetime

from a3_constructa.demo.masiha.common import (
	COMPANY, approve_levels, as_user, at, comment, day, log, project, transition, wh,
)
from a3_constructa.demo.masiha.setup import require_approval_levels
from a3_constructa.overrides.approvals import reject

def run():
	require_approval_levels()
	# The 2,000-bag cement request is only made here.
	if frappe.db.exists("Material Request Item", {"item_code": "CEM-425-50", "qty": 2000, "wbs": "MSS-W-ES"}):
		log("approval documents already present")
		return
	made = [
		mr_adhesive(), mr_cement(), mr_paint_rejected(),
		po_rebar(), po_grout_waiting(), po_paint_over_budget(), po_spacers_amended(),
	]
	log("approvals: " + ", ".join(made))


# ---------------------------------------------------------------- helpers
def _mr(item, qty, rate, wbs, cost_code, when, note):
	with as_user("requester"):
		mr = frappe.get_doc({
			"doctype": "Material Request", "material_request_type": "Purchase", "company": COMPANY,
			"transaction_date": day(when), "schedule_date": day(when + 21),
			"items": [{"item_code": item, "qty": qty, "rate": rate, "schedule_date": getdate(day(when + 21)),
			           "warehouse": wh("Mbandaka Site Store"), "project": project(), "wbs": wbs, "cost_code": cost_code}],
		})
		mr.insert(ignore_permissions=True)
	_backdate("Material Request", mr.name, when)
	comment("Material Request", mr.name, note, "requester", at(when, 8, 5))
	transition("Material Request", mr.name, "Submit for Verification", "requester", at(when, 9))
	transition("Material Request", mr.name, "Verify Stock", "stores", at(when, 14))
	return mr.name


def _po(supplier, item, qty, rate, wbs, cost_code, when, note):
	with as_user("buyer"):
		po = frappe.get_doc({
			"doctype": "Purchase Order", "company": COMPANY, "supplier": supplier, "transaction_date": day(when),
			"schedule_date": day(when + 21), "project": project(), "set_warehouse": wh("Mbandaka Site Store"),
			"items": [{"item_code": item, "qty": qty, "rate": rate, "schedule_date": getdate(day(when + 21)),
			           "warehouse": wh("Mbandaka Site Store"), "project": project(), "wbs": wbs, "cost_code": cost_code}],
		})
		po.insert(ignore_permissions=True)
	_backdate("Purchase Order", po.name, when)
	transition("Purchase Order", po.name, "Submit for Approval", "buyer", at(when, 10))
	comment("Purchase Order", po.name, note, "buyer", at(when, 10, 5))
	return po.name


def _backdate(doctype, name, when):
	frappe.db.set_value(doctype, name, "creation", at(when, 8), update_modified=False)


# ---------------------------------------------------------------- requests
def mr_adhesive():
	name = _mr("FIN-ADH-C2", 40, 9.80, "MSS-W-FL-A", "MSS-CC-FIN-M", -9, "Tile adhesive top-up for the ground-floor corridors")
	transition("Material Request", name, "Approve", "pm", at(-8, 11), "Within the flooring allocation.")
	return f"{name} approved"


def mr_cement():
	name = _mr("CEM-425-50", 2000, 11.05, "MSS-W-ES", "MSS-CC-STR-M", -5, "Cement for the second-floor slab pour")
	approve_levels("Material Request", name, at(-4, 10), upto=1, note="Quantity checked against the slab take-off.")
	return f"{name} waiting for level 2"


def mr_paint_rejected():
	name = _mr("PNT-EMU-20", 8, 66.00, "MSS-W-FL-B", "MSS-CC-FIN-M", -3, "Emulsion for the first-floor offices")
	with as_user("pm"):
		reject("Material Request", name, "Wrong WBS and cost code: paint belongs to Painting (MSS-W-PT / MSS-CC-PNT-M). Correct and resubmit.")
	frappe.db.set_value("Approval Log", {"parent": name}, "on", at(-2, 16), update_modified=False)
	return f"{name} rejected"


# ---------------------------------------------------------------- orders
def po_rebar():
	name = _po("Congo Steel & Cement SARL", "STL-Y16", 32, 975.00, "MSS-W-ES", "MSS-CC-STR-M", -4,
	           "Rebar Y16 for the second-floor slab, second lot.")
	approve_levels("Purchase Order", name, at(-3, 15), upto=1, note="Price as per the framework quote.")
	return f"{name} waiting for level 2"


def po_grout_waiting():
	name = _po("Kinshasa Building Supplies SARL", "FIN-GRT-CG2", 60, 6.40, "MSS-W-FL-B", "MSS-CC-FIN-M", -6,
	           "Grout for the first-floor tiling.")
	return f"{name} waiting for level 1"


def po_paint_over_budget():
	name = _po("Quincaillerie du Fleuve", "PNT-EMU-20", 200, 64.00, "MSS-W-PT", "MSS-CC-PNT-M", -7,
	           "Emulsion for all internal walls: the take-off came out higher than the BOQ.")
	transition("Purchase Order", name, "Approve", "procurement", at(-6, 11),
	           "Approved over the painting budget; QS to raise a budget transfer.")
	frappe.local.message_log = []
	return f"{name} submitted over budget"


def po_spacers_amended():
	name = _po("Quincaillerie du Fleuve", "FIN-SPC-3", 50, 4.40, "MSS-W-FL-B", "MSS-CC-FIN-M", -12,
	           "Tile spacers for the first floor.")
	transition("Purchase Order", name, "Approve", "procurement", at(-11, 9))
	with as_user("pm"):  # A3 Constructa Admin may cancel
		po = frappe.get_doc("Purchase Order", name)
		po.flags.ignore_permissions = True
		po.cancel()
		amended = frappe.copy_doc(po)
		amended.amended_from = po.name
		amended.workflow_state = None
		amended.items[0].qty = 30
		amended.flags.ignore_permissions = True
		amended.insert()
	comment("Purchase Order", amended.name, "Supplier has only 30 bags in stock; reordered for 30.", "buyer", at(-2, 9))
	return f"{name} cancelled, {amended.name} waiting for level 1"
