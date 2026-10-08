# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-R: the cases the refreshed overview tabs check for that the earlier stages left out.

- Asset & Equipment: the hired crane stood waiting for steel two more days (1 h
  worked of 8 or 9 on site), so its month falls under 50% utilisation; the
  excavator's log from four days ago waits for the operator's sheet (draft).
- Planning & Budgeting: emulsion paint typed onto the hospital's plan by hand
  with no date yet, so it has no PR date to be late against.
- Master data: a new helper joins the general labour pool before his salary
  structure is set up, so the crew has a member on no daily rate; an inspection
  alert set up for a site engineer who has since left (user disabled) reaches
  nobody and has not run yet; a painting line on the hospital tender is
  estimated with the painters' rate but no output per day, and the paint with
  no price yet.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, log, project
from a3_constructa.demo.masiha.equipment import CRANE_ITEM, EXCAVATOR, HOSPITAL_SITE, equipment_log

PLAN_REMARK = "Colour and quantity to confirm with the architect"
LEFT_USER = "joseph.mbala@masiha.demo"
RULE = "Inspections overdue (site engineer)"
HELPER = ("Bienvenu", "Likambo")
TENDER = "Hospital extension: maternity and theatre block"


def run():
	made = [idle_crane(), draft_log(), undated_plan_line(), new_helper(), rule_nobody_receives(), unfinished_estimate()]
	log("Overview refresh: " + "; ".join(m for m in made if m))


def idle_crane():
	crane = frappe.db.get_value("Asset", {"item_code": CRANE_ITEM}, "name")
	if not crane or frappe.db.exists("Equipment Log", {"asset": crane, "log_date": day(-3)}):
		return None
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")
	site = (hospital, HOSPITAL_SITE, "HGR-W-ES")
	logs = [equipment_log(crane, -3, site, 17, 18, 1, 7, 0, "Steel still at Matadi; one cage lifted, stood by"),
	        equipment_log(crane, -2, site, 18, 19, 1, 8, 0, "Stood by for the steel delivery")]
	return f"crane {crane} idle: {', '.join(logs)}"


def draft_log():
	if frappe.db.exists("Equipment Log", {"asset": EXCAVATOR, "log_date": day(-4)}):
		return None
	name = equipment_log(EXCAVATOR, -4, (project(), "Mbandaka Site", "MSS-W-ES"), 0, 0, 6, 1, 0,
	                     "Backfill to pads, gridline E: operator's sheet not yet handed in", submit=False)
	comment("Equipment Log", name, "Waiting for Ekofo's day sheet before I submit; hours are from the foreman.", "requester", at(-3, 8))
	return f"draft log {name}"


def undated_plan_line():
	# On the hospital's plan: the Administrative Centre's paint is already requested,
	# and a line is linked to any request for its item on the project.
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")
	plan = frappe.db.get_value("Procurement Plan", {"project": hospital, "status": ["not in", ["Cancelled", "Completed"]]}, "name")
	if not plan or frappe.db.exists("Procurement Plan Item", {"remarks": PLAN_REMARK}):
		return None
	paint = frappe.db.get_value("Item", {"item_name": ["like", "%mulsion%"]}, ["name", "stock_uom"], as_dict=True)
	if not paint:
		return None
	doc = frappe.get_doc("Procurement Plan", plan)
	doc.append("items", {"item_code": paint.name, "procurement_route": "Buy", "anticipated_qty": 60, "uom": paint.stock_uom,
	                     "lead_time_days": 14, "remarks": PLAN_REMARK})
	doc.flags.ignore_permissions = True
	doc.save()
	return f"undated line on {plan}"


def new_helper():
	pool = frappe.db.get_value("Crew", {"crew_name": "General labour pool"}, "name")
	if not pool:
		return None
	employee = frappe.db.get_value("Employee", {"first_name": HELPER[0], "last_name": HELPER[1], "company": COMPANY}, "name")
	if not employee:
		e = frappe.get_doc({"doctype": "Employee", "first_name": HELPER[0], "last_name": HELPER[1], "gender": "Male", "company": COMPANY,
		                    "date_of_birth": "1998-06-12", "date_of_joining": day(-3), "status": "Active", "designation": "Site Helper",
		                    "department": f"Operations - {frappe.get_cached_value('Company', COMPANY, 'abbr')}"})
		e.flags.ignore_permissions = True
		e.insert()
		employee = e.name
	crew = frappe.get_doc("Crew", pool)
	if any(m.employee == employee for m in crew.members):
		return None
	crew.append("members", {"employee": employee, "role": "Helper", "is_active": 1})
	with as_user("pm"):
		crew.flags.ignore_permissions = True
		crew.save()
	comment("Crew", pool, "Bienvenu started Monday; HR to set up his daily wage.", "pm", at(-3, 7))
	return f"{employee} on {pool} with no daily rate"


def rule_nobody_receives():
	if frappe.db.exists("Alert Rule", RULE):
		return None
	if not frappe.db.exists("User", LEFT_USER):
		u = frappe.get_doc({"doctype": "User", "email": LEFT_USER, "first_name": "Joseph", "last_name": "Mbala", "enabled": 0,
		                    "send_welcome_email": 0, "user_type": "System User"})
		u.flags.ignore_permissions = True
		u.insert()
	r = frappe.get_doc({"doctype": "Alert Rule", "rule_name": RULE, "condition": "Task slipped", "threshold": 3, "channel": "In-app",
	                    "frequency": "Daily", "is_active": 1, "recipients": [{"recipient_type": "User", "user": LEFT_USER}]})
	r.flags.ignore_permissions = True
	r.insert()
	return f"alert rule {r.name} for a user who has left"


def unfinished_estimate():
	# The hospital's tender lines are all priced; its draft budget BOQ is not yet
	# approved, so a sheet on it changes no budget.
	opp = frappe.db.get_value("Opportunity", {"title": TENDER}, "name")
	line = boq = None
	for boq in frappe.get_all("BOQ", filters={"opportunity": opp, "status": "Draft"}, order_by="boq_stage desc", pluck="name") if opp else []:
		priced = set(frappe.get_all("Estimate Sheet", filters={"boq": boq}, pluck="boq_item"))
		open_lines = [r for r in frappe.get_all("BOQ Item", filters={"parent": boq, "is_allowance": 0},
		                                        fields=["name", "boq_ref", "description"], order_by="idx") if r.name not in priced]
		line = next((r for r in open_lines if "aint" in (r.description or "")), None) or (open_lines[0] if open_lines else None)
		if line:
			break
	if not line or frappe.db.exists("Estimate Resource", {"description": "Painters (2) and a helper"}):
		return None
	with as_user("qs"):
		sheet = frappe.new_doc("Estimate Sheet")
		sheet.boq, sheet.boq_item = boq, line.name
		sheet.append("resources", {"resource_type": "Material", "description": "Emulsion paint, 20 L pail (price awaited)", "qty_per_unit": 0.02,
		                           "wastage_percent": 5, "rate_source": "Manual"})
		sheet.append("resources", {"resource_type": "Labour", "description": "Painters (2) and a helper", "rate": 85, "rate_source": "Manual"})
		sheet.flags.ignore_permissions = True
		sheet.insert()
	return f"estimate {sheet.name} on {line.boq_ref} left unfinished"
