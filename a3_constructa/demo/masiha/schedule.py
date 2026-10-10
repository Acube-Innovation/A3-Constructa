# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06A: the Administrative Centre's programme on the WBS.

Each task gets its WBS node (W-06 set them), cost code, planned quantity and
foreman, and its links get their type and lag: the frame started 45 days into the
earthworks (SS +45), blockwork 50 days into the frame (SS +50), tiling 10 days into
the blockwork (SS +10), finishes 40 days into the roof (SS +40); the roof and MEP
follow the frame (FS); testing and commissioning runs on from the finishes and MEP to
the contract completion date. Doors and windows is a group of three weighted sub-tasks
(40 / 35 / 25). The award's milestones become milestone tasks, the frame's tied
to the frame's finish (FF). The forward and backward pass then marks the critical
path.
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, day, log, project

# subject: (cost code, planned qty, uom, foreman (first, last), [(predecessor, type, lag)])
TASKS = {
	"Site establishment": ("MSS-CC-SITE", None, None, None, []),
	"Earthworks and substructure": ("MSS-CC-STR-M", 4200, "Cubic Meter", None, [("Site establishment", "FS", 0)]),
	"Concrete frame": ("MSS-CC-STR-M", 1350, "Cubic Meter", ("Moïse", "Kanku"), [("Earthworks and substructure", "SS", 45)]),
	"Blockwork": ("MSS-CC-STR-M", 2600, "Square Meter", ("Papy", "Tshilombo"), [("Concrete frame", "SS", 50)]),
	"Floor tiling, ground floor": ("MSS-CC-FIN-S", 600, "Square Meter", ("Jean-Pierre", "Mukendi"), [("Blockwork", "SS", 10)]),
	"Roof structure and covering": ("MSS-CC-STR-M", 1450, "Square Meter", None, [("Concrete frame", "FS", 0)]),
	"MEP first fix": ("MSS-CC-MEP-M", None, None, None, [("Concrete frame", "FS", 0), ("Blockwork", "SS", 30)]),
	"Finishes and handover": ("MSS-CC-FIN-M", None, None, None, [("Roof structure and covering", "SS", 40)]),
}
# The programme runs on to the contract completion date through commissioning.
COMMISSIONING = ("Testing, commissioning and handover", 121, 206, "MSS-W-MEP", "MSS-CC-MEP-M",
                 [("Finishes and handover", "FS", 0), ("MEP first fix", "FS", 0)])
# Doors and windows: a group of weighted sub-tasks
DOORS = [("Door frames and doors", 30, 55, 40, [("Blockwork", "FF", 0)]), ("Windows and glazing", 40, 75, 35, [("Door frames and doors", "SS", 10)]),
         ("Ironmongery and adjustments", 76, 90, 25, [("Windows and glazing", "FS", 0)])]


def run():
	p = project()
	if frappe.db.exists("Task", {"project": p, "subject": "Doors and windows"}):
		log("schedule already on the WBS")
		return
	names = dict(frappe.get_all("Task", filters={"project": p}, fields=["subject", "name"], as_list=True))
	# Tasks made before the WBS was required take the nodes W-06's programme names.
	from a3_constructa.demo.masiha.operations import ADMIN, HOSPITAL

	for row in ADMIN + HOSPITAL:
		for name in frappe.get_all("Task", filters={"subject": row[0], "wbs": ["is", "not set"]}, pluck="name"):
			frappe.db.set_value("Task", name, "wbs", row[6], update_modified=False)
	frappe.flags.a3_task_cascade = 1  # one pass at the end
	frappe.flags.a3_no_reschedule = 1  # links and dates are set together here
	try:
		with as_user("pm"):
			for subject, (cost_code, qty, uom, foreman, links) in TASKS.items():
				t = frappe.get_doc("Task", names[subject])
				t.update({"cost_code": cost_code, "planned_qty": qty, "uom": uom, "foreman": employee(foreman)})
				t.set("depends_on", [{"task": names[pred], "dependency_type": kind, "lag_days": lag} for pred, kind, lag in links])
				t.flags.ignore_permissions = True
				t.save()
			group = frappe.get_doc({"doctype": "Task", "subject": "Doors and windows", "project": p, "is_group": 1, "wbs": "MSS-W-DW",
			                        "cost_code": "MSS-CC-DW-M", "exp_start_date": day(30), "exp_end_date": day(90), "status": "Open"})
			group.flags.ignore_permissions = True
			group.insert()
			subject, start, end, wbs, cost_code, links = COMMISSIONING
			t = frappe.get_doc({"doctype": "Task", "subject": subject, "project": p, "wbs": wbs, "cost_code": cost_code, "status": "Open",
			                    "exp_start_date": day(start), "exp_end_date": day(end),
			                    "depends_on": [{"task": names[pred], "dependency_type": kind, "lag_days": lag} for pred, kind, lag in links]})
			t.flags.ignore_permissions = True
			t.insert()
			names[subject] = t.name
			for subject, start, end, weight, links in DOORS:
				t = frappe.get_doc({"doctype": "Task", "subject": subject, "project": p, "parent_task": group.name, "task_weight": weight,
				                    "wbs": "MSS-W-DW", "cost_code": "MSS-CC-DW-M", "exp_start_date": day(start), "exp_end_date": day(end),
				                    "status": "Open", "depends_on": [{"task": names[pred], "dependency_type": kind, "lag_days": lag} for pred, kind, lag in links]})
				t.flags.ignore_permissions = True
				t.insert()
				names[subject] = t.name
			from a3_constructa.overrides.task import create_schedule_milestones

			award = frappe.db.get_value("Awarded Quotation", {"project": p}, "name")
			milestones = create_schedule_milestones(award)
			for milestone, pred in (("Reinforced concrete frame", "Concrete frame"), ("MEP, testing and handover", "Testing, commissioning and handover")):
				ms = frappe.db.get_value("Task", {"project": p, "subject": ["like", f"Milestone: {milestone}%"]}, "name")
				if ms:
					m = frappe.get_doc("Task", ms)
					m.set("depends_on", [{"task": names[pred], "dependency_type": "FF", "lag_days": 0}])
					m.flags.ignore_permissions = True
					m.save()
	finally:
		frappe.flags.a3_task_cascade = 0
		frappe.flags.a3_no_reschedule = 0
	from a3_constructa.overrides.task import critical_path

	result = critical_path(p)
	critical = [n for n, r in result.items() if r["critical"]]
	log(f"Schedule: {len(TASKS)} tasks on the WBS, Doors and windows in 3 weighted sub-tasks, {len(milestones)} milestone tasks; "
	    f"{len(critical)} critical")


def employee(name):
	if not name:
		return None
	return frappe.db.get_value("Employee", {"first_name": name[0], "last_name": name[1]}, "name")
