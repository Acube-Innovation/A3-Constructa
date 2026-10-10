# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06E: the three-week look-ahead.

Administrative Centre - the constraints on the next three weeks:
- the Mbandaka Site Store is the project's store; ground-floor tiling is short of
  tile adhesive for the 40% still to lay (porcelain and grout are covered by stock
  and the open order);
- the frame now has the general labour pool and is clear; the roof waits on the
  frame, has no crew and no work-at-height permit yet; MEP first fix waits on the
  frame, has no coordinated drawings, and its electricians are still on the
  committee wing rewiring.

Provincial Assembly committee wing - a refurbishment planned week by week:
- last week four tasks were committed and three started (PPC 75%); the ceiling
  grid did not, because the partitions ran late;
- next week plastering and the east windows are Ready to commit; the floor screed
  is not - its cement isn't in the committee wing store; the air-conditioning
  needs two scissor lifts and the site has one.

Dates hang off this week's Monday, so last week and next week are always whole
weeks.
"""

import frappe
from frappe.utils import add_days, getdate, today

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, insert, log, project, wh

WING = "Provincial Assembly committee wing"
WING_STORE = "Committee Wing Store"
WING_SITE = "Provincial Assembly Site"
LIFT_ITEM = "EQ-SCL-8M"
# name, trade
CREWS = [("Electricians", "Electrical"), ("Plumbers", "Plumbing"), ("Drylining team", "Carpentry"),
         ("Plasterers", "Masonry"), ("Glazing team", "Carpentry"), ("Screed team", "Concrete")]
# Administrative Centre: subject -> crew, permit ready, drawings ready
ADMIN = {
	"Concrete frame": ("General labour pool", 1, 1),
	"Blockwork": (None, 1, 1),
	"Floor tiling, ground floor": (None, 1, 1),
	"Roof structure and covering": (None, 0, 1),
	"MEP first fix": ("Electricians", 1, 0),
}


def run():
	mon = getdate(add_days(today(), -getdate(today()).weekday()))
	stores()
	crews = make_crews()
	admin(crews)
	wing = frappe.db.get_value("Project", {"project_name": WING, "company": COMPANY}, "name")
	if frappe.db.exists("Task", {"project": wing, "subject": "Strip-out and demolition"}):
		log("committee wing programme already present")
		return
	lift(wing)
	made = wing_tasks(wing, crews, mon)
	log(f"Look-ahead: committee wing programme {made[0]} – {made[-1]} ({len(made)} tasks); last week committed 4, started 3")


def stores():
	frappe.db.set_value("Warehouse", wh("Mbandaka Site Store"), "project", project(), update_modified=False)
	wing = frappe.db.get_value("Project", {"project_name": WING, "company": COMPANY}, "name")
	if not frappe.db.exists("Warehouse", wh(WING_STORE)):
		parent = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 1}, "name")
		insert({"doctype": "Warehouse", "warehouse_name": WING_STORE, "company": COMPANY, "parent_warehouse": parent,
		        "warehouse_type": "Site", "project": wing})


def make_crews():
	out = {"General labour pool": frappe.db.get_value("Crew", {"crew_name": "General labour pool"}, "name")}
	wing = frappe.db.get_value("Project", {"project_name": WING, "company": COMPANY}, "name")
	for name, trade in CREWS:
		out[name] = frappe.db.get_value("Crew", {"crew_name": name, "company": COMPANY}, "name")
		if out[name]:
			continue
		with as_user("pm"):
			c = insert({"doctype": "Crew", "crew_name": name, "trade": trade, "company": COMPANY, "project": wing, "is_active": 1})
		frappe.db.set_value("Crew", c.name, "creation", at(-60, 9), update_modified=False)
		out[name] = c.name
	return out


def admin(crews):
	p = project()
	for subject, (crew, permit, drawings) in ADMIN.items():
		name = frappe.db.get_value("Task", {"project": p, "subject": subject})
		values = {"permit_ready": permit, "drawings_ready": drawings}
		if crew:
			values["crew"] = crews[crew]
		frappe.db.set_value("Task", name, values, update_modified=False)
	roof = frappe.db.get_value("Task", {"project": p, "subject": "Roof structure and covering"})
	mep = frappe.db.get_value("Task", {"project": p, "subject": "MEP first fix"})
	if not frappe.db.exists("Comment", {"reference_name": roof, "content": ["like", "%work-at-height%"]}):
		comment("Task", roof, "Work-at-height permit applied for; the safety officer inspects the edge protection before issuing it.", "requester", at(-2, 15))
		comment("Task", mep, "Coordinated MEP drawings (rev C) are still with the design team: due Friday.", "pm", at(-1, 11))


def lift(wing):
	if not frappe.db.exists("Location", WING_SITE):
		insert({"doctype": "Location", "location_name": WING_SITE})
	if not frappe.db.exists("Item", LIFT_ITEM):
		insert({"doctype": "Item", "item_code": LIFT_ITEM, "item_name": "Scissor lift 8 m", "item_group": "Heavy Equipment Items",
		        "stock_uom": "Nos", "is_stock_item": 0, "is_fixed_asset": 1, "asset_category": "Small Machinery",
		        "include_item_in_manufacturing": 0})
	if frappe.db.exists("Asset", {"item_code": LIFT_ITEM, "project": wing}):
		return
	with as_user("pm"):
		a = frappe.get_doc({"doctype": "Asset", "asset_name": "Scissor lift 8 m (hired)", "item_code": LIFT_ITEM, "company": COMPANY,
		                    "asset_category": "Small Machinery", "location": WING_SITE, "is_existing_asset": 1,
		                    "available_for_use_date": add_days(today(), -30), "purchase_date": add_days(today(), -30),
		                    "calculate_depreciation": 0, "gross_purchase_amount": 18_000, "is_hired": 1, "meter_type": "Hours",
		                    "project": wing, "make": "Genie", "model": "GS-2632"})
		a.flags.ignore_permissions = True
		a.insert()
	comment("Asset", a.name, "Hired by the month for the ceilings and high-level services in the committee wing. One on site.", "pm", at(-30, 9))


def wing_tasks(wing, crews, mon):
	d = lambda n: add_days(mon, n)  # noqa: E731
	# subject, start, end, status, crew, permit, drawings, depends [(subject, type)], committed, started, progress, done on
	plan = [
		("Strip-out and demolition", -98, -64, "Completed", "Drylining team", 1, 1, [], None, -98, 100, -64),
		("Partition walls, ground and first floor", -23, 4, "Working", "Drylining team", 1, 1, [("Strip-out and demolition", "FS")], None, -23, 90, None),
		("Fire-stopping to service risers", -6, -2, "Completed", "Plumbers", 1, 1, [("Strip-out and demolition", "FS")], -7, -6, 100, -2),
		("Electrical rewiring, first fix", -7, 25, "Working", "Electricians", 1, 1, [("Strip-out and demolition", "FS")], -7, -6, 20, None),
		("Plumbing to the WCs", -5, 13, "Working", "Plumbers", 1, 1, [("Strip-out and demolition", "FS")], -7, -4, 25, None),
		("Ceiling grid, committee rooms", 14, 25, "Open", "Drylining team", 1, 1, [("Partition walls, ground and first floor", "FS")], -7, None, 0, None),
		("Plastering and skim coat", 7, 25, "Open", "Plasterers", 1, 1, [("Partition walls, ground and first floor", "SS")], None, None, 0, None),
		("Window replacement, east elevation", 9, 18, "Open", "Glazing team", 1, 1, [("Strip-out and demolition", "FS")], None, None, 0, None),
		("Floor screed, committee rooms", 10, 16, "Open", "Screed team", 1, 1, [("Strip-out and demolition", "FS")], None, None, 0, None),
		("Air-conditioning units", 16, 32, "Open", None, 1, 0, [("Electrical rewiring, first fix", "SS")], None, None, 0, None),
	]
	names = {}
	frappe.flags.a3_task_cascade = 1
	frappe.flags.a3_no_reschedule = 1
	try:
		with as_user("pm"):
			for subject, start, end, status, crew, permit, drawings, deps, committed, started, progress, done in plan:
				t = frappe.get_doc({"doctype": "Task", "subject": subject, "project": wing, "wbs": "PAC-W", "status": "Open",
				                    "exp_start_date": d(start), "exp_end_date": d(end), "crew": crews.get(crew),
				                    "permit_ready": permit, "drawings_ready": drawings, "progress_method": "Manual",
				                    "depends_on": [{"task": names[s], "dependency_type": k} for s, k in deps]})
				if subject == "Floor screed, committee rooms":
					t.append("resources", {"resource_type": "Material", "item_code": "CEM-425-50", "qty_per_day": 160, "days": 1,
					                       "need_by_date": d(start)})
				if subject == "Air-conditioning units":
					t.append("resources", {"resource_type": "Equipment", "asset_category": "Small Machinery", "description": "Scissor lifts",
					                       "qty_per_day": 2, "days": 5})
				t.flags.ignore_permissions = True
				t.insert()
				names[subject] = t.name
				values = {"progress": progress, "committed_week": d(committed) if committed is not None else None,
				          "act_start_date": d(started) if started is not None else None}
				if status == "Completed":
					values.update(status="Completed", completed_on=d(done), act_end_date=d(done))
				elif status != "Open":
					values["status"] = status
				frappe.db.set_value("Task", t.name, values, update_modified=False)
				t.reload()
				from a3_constructa.overrides.task_progress import forecast

				forecast(t)
				frappe.db.set_value("Task", t.name, {"remaining_duration": t.remaining_duration, "forecast_end": t.forecast_end},
				                    update_modified=False)
				frappe.db.set_value("Task", t.name, "creation", at(-100 if start < -60 else -30, 9), update_modified=False)
	finally:
		frappe.flags.a3_task_cascade = 0
		frappe.flags.a3_no_reschedule = 0
	comment("Task", names["Ceiling grid, committee rooms"],
	        "Not started last week as committed: the partitions ran late, so the grid moves two weeks.", "requester", at(-3, 16))
	comment("Task", names["Floor screed, committee rooms"],
	        "160 bags of cement needed in the committee wing store; nothing ordered yet.", "requester", at(-1, 10))
	from a3_constructa.overrides.task_progress import update_wbs_progress

	update_wbs_progress(wing)
	return list(names.values())
