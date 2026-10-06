# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""W-06: the jobs' programmes as tasks, so Project Operations' Master Schedule and its
Gantt chart have something to show. P-06A puts them on the WBS with quantities.

Administrative Centre: site establishment and earthworks done; the concrete frame
running late (it was due on 17 September, as the award's milestone says); blockwork
and ground-floor tiling under way; roof, MEP and finishes to come.
Hospital: its programme from site possession in four weeks, following the award's milestones.
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, at, day, log, project

# subject, start, end, status, progress, depends on (subject)
ADMIN = [
	("Site establishment", -154, -135, "Completed", 100, None),
	("Earthworks and substructure", -135, -60, "Completed", 100, "Site establishment"),
	("Concrete frame", -90, -19, "Working", 70, "Earthworks and substructure"),
	("Blockwork", -40, 30, "Working", 35, "Earthworks and substructure"),
	("Floor tiling, ground floor", -30, 20, "Working", 60, "Earthworks and substructure"),
	("Roof structure and covering", 5, 45, "Open", 0, "Concrete frame"),
	("MEP first fix", 10, 70, "Open", 0, "Concrete frame"),
	("Finishes and handover", 45, 120, "Open", 0, "Roof structure and covering"),
]
HOSPITAL = [
	("Mobilisation and site set-up", 27, 60, "Open", 0, None),
	("Substructure", 60, 180, "Open", 0, "Mobilisation and site set-up"),
	("Frame and envelope", 150, 330, "Open", 0, "Substructure"),
]


def run():
	if frappe.db.exists("Task", {"project": project()}):
		log("tasks already present")
		return
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")
	made = programme(project(), ADMIN) + programme(hospital, HOSPITAL)
	log(f"Tasks: {made} on the Administrative Centre and the hospital")


def programme(project_name, rows):
	names = {}
	with as_user("pm"):
		for subject, start, end, status, progress, depends in rows:
			t = frappe.get_doc({"doctype": "Task", "subject": subject, "project": project_name, "exp_start_date": day(start),
			                    "exp_end_date": day(end), "status": status, "progress": progress,
			                    "completed_on": day(end) if status == "Completed" else None,
			                    "depends_on": [{"task": names[depends]}] if depends else []})
			t.flags.ignore_permissions = True
			t.insert()
			frappe.db.set_value("Task", t.name, {"creation": at(min(start, -1), 9)}, update_modified=False)
			names[subject] = t.name
	# ERPNext marks a task past its expected end Overdue; the frame is.
	frame = names.get("Concrete frame")
	if frame:
		frappe.db.set_value("Task", frame, "status", "Overdue", update_modified=False)
	return len(rows)
