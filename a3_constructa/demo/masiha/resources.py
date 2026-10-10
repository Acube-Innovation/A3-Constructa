# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06B: resource-loaded tasks.

Administrative Centre: tiling by Tiling gang A and blockwork by the Blockwork gang
(their crews' headcount), with the tiling materials needed at its start; the roof
needs six carpenters and a mobile crane for ten days; MEP first fix four
electricians and three plumbers.
Hospital: the substructure is tied to its BOQ line (A/02/03, 186 m³ of reinforced
concrete) and two tasks are added on theirs, foundation excavation (A/01/02, 640 m³)
and the foundation rebar (A/02/04, 22.5 t); all three are filled from the tender's
estimates (P-02C).
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, day, log, project

HOSPITAL_BUDGET_REF = {"Substructure": "A/02/03"}
NEW_HOSPITAL = [("Foundation excavation", 61, 90, "A/01/02", 640, "Cubic Meter", [("Mobilisation and site set-up", "FS", 0)]),
                ("Rebar to foundations", 70, 110, "A/02/04", 22.5, "Tonne", [("Foundation excavation", "SS", 9)])]


def run():
	p = project()
	if frappe.db.exists("Task Resource", {"parenttype": "Task"}):
		log("task resources already present")
		return
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")
	frappe.db.set_value("Task", {"project": hospital, "subject": "Mobilisation and site set-up"}, "exp_end_date", day(59))  # FS: not the same day
	names = dict(frappe.get_all("Task", filters={"project": ["in", [p, hospital]]}, fields=["subject", "name"], as_list=True))
	crew = lambda n: frappe.db.get_value("Crew", {"crew_name": n}, "name")
	frappe.flags.a3_no_reschedule = 1
	try:
		with as_user("pm"):
			edit(names["Floor tiling, ground floor"], crew=crew("Tiling gang A"), resources=[
				{"resource_type": "Labour", "crew": crew("Tiling gang A")},
				{"resource_type": "Material", "item_code": "FIN-POR-600", "qty_per_day": 600, "days": 1, "description": "Porcelain tile 600 x 600, WBS A"},
				{"resource_type": "Material", "item_code": "FIN-ADH-C2", "qty_per_day": 156, "days": 1, "description": "Tile adhesive C2TE"},
				{"resource_type": "Material", "item_code": "FIN-GRT-CG2", "qty_per_day": 54, "days": 1, "description": "Tile grout CG2"}])
			edit(names["Blockwork"], crew=crew("Blockwork gang"), resources=[{"resource_type": "Labour", "crew": crew("Blockwork gang")}])
			edit(names["Roof structure and covering"], resources=[
				{"resource_type": "Labour", "trade": "Carpentry", "qty_per_day": 6, "description": "Roof carpenters"},
				{"resource_type": "Equipment", "asset_category": "Heavy Equipment", "qty_per_day": 1, "days": 10, "description": "Mobile crane 25 t for the trusses"}])
			edit(names["MEP first fix"], resources=[
				{"resource_type": "Labour", "trade": "Electrical", "qty_per_day": 4, "description": "Electricians"},
				{"resource_type": "Labour", "trade": "Plumbing", "qty_per_day": 3, "description": "Plumbers"}])
			budget = frappe.db.get_value("BOQ", {"project": hospital, "boq_stage": "Budget", "docstatus": ["<", 2]}, "name")
			line = lambda ref: frappe.db.get_value("BOQ Item", {"parent": budget, "boq_ref": ref}, ["name", "boq_qty", "uom"], as_dict=True)
			for subject, ref in HOSPITAL_BUDGET_REF.items():
				l = line(ref)
				edit(names[subject], boq=budget, boq_item=l.name, planned_qty=l.boq_qty, uom=l.uom)
			for subject, start, end, ref, qty, uom, links in NEW_HOSPITAL:
				l = line(ref)
				t = frappe.get_doc({"doctype": "Task", "subject": subject, "project": hospital, "wbs": "HGR-W-ES", "status": "Open",
				                    "exp_start_date": day(start), "exp_end_date": day(end), "boq": budget, "boq_item": l.name, "planned_qty": qty, "uom": uom,
				                    "cost_code": "MSS-CC-STR-M",
				                    "depends_on": [{"task": names[pred], "dependency_type": kind, "lag_days": lag} for pred, kind, lag in links]})
				t.flags.ignore_permissions = True
				t.insert()
				names[subject] = t.name
	finally:
		frappe.flags.a3_no_reschedule = 0
	from a3_constructa.overrides.task_resources import fill_from_estimate
	from a3_constructa.overrides.task import critical_path

	filled = []
	with as_user("pm"):
		for subject in list(HOSPITAL_BUDGET_REF) + [n[0] for n in NEW_HOSPITAL]:
			r = fill_from_estimate(names[subject])
			filled.append(f"{subject}: {r['rows']} rows from {r['estimate_sheet']}")
	critical_path(hospital)
	critical_path(p)
	log("Resources: Administrative Centre crews, plant and materials; hospital " + "; ".join(filled))


def edit(name, **values):
	t = frappe.get_doc("Task", name)
	resources = values.pop("resources", None)
	t.update(values)
	if resources is not None:
		t.set("resources", resources)
	t.flags.ignore_permissions = True
	t.save()
