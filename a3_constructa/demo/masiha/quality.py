# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06G: inspections and NCRs on the Administrative Centre.

Checklists for concrete pre-pour, blockwork and floor tiling, on the task types
Concrete works, Blockwork and Floor finishes.
- Level 2 slab pre-pour (frame, Hold point): accepted, witnessed by the client's
  engineer.
- Ground-floor tiling, zone 4 (Surveillance): six hollow tiles on the tap test -
  rejected; the NCR is at Action Taken (tiles relaid, waiting for the re-check),
  two days past its due date; $1,150.
- Level 1 blockwork, grid C (Witness): 12 mm out of plumb against 5 allowed -
  rejected; the NCR is Open with the blockwork foreman, $640.
- An NCR from August, honeycombing at column C4, closed after a repair ($2,400).
- Level 3 columns pre-pour (Hold point): requested today, not yet inspected.
"""

import frappe
from frappe.utils import add_days, today

from a3_constructa.demo.masiha.common import as_user, at, comment, insert, log, project, user

# parameter, numeric, min, max, value
CHECKLISTS = {
	"Concrete pre-pour": [("Reinforcement cover (mm)", 1, 40, 50, None), ("Formwork line and level (mm)", 1, -5, 5, None),
	                      ("Embedded items in place", 0, None, None, "Yes"), ("Formwork clean and release agent applied", 0, None, None, "Yes")],
	"Blockwork": [("Plumb deviation per storey (mm)", 1, 0, 5, None), ("Line deviation over 5 m (mm)", 1, 0, 5, None),
	              ("Mortar joint thickness (mm)", 1, 8, 12, None), ("Wall ties installed", 0, None, None, "Yes")],
	"Floor tiling": [("Hollow tiles on tap test", 0, None, None, "None"), ("Lippage (mm)", 1, 0, 1, None), ("Joint width (mm)", 1, 2, 4, None)],
}
TYPES = {"Concrete works": "Concrete pre-pour", "Blockwork": "Blockwork", "Floor finishes": "Floor tiling"}
TASK_TYPES = {"Concrete frame": "Concrete works", "Blockwork": "Blockwork", "Floor tiling, ground floor": "Floor finishes"}


def run():
	p = project()
	masters()
	for subject, ttype in TASK_TYPES.items():
		frappe.db.set_value("Task", {"project": p, "subject": subject}, "type", ttype, update_modified=False)
	if frappe.db.exists("Quality Inspection", {"project": p}):
		log("inspections already present")
		return
	task = lambda s: frappe.db.get_value("Task", {"project": p, "subject": s})  # noqa: E731
	emp = lambda first, last: frappe.db.get_value("Employee", {"first_name": first, "last_name": last})  # noqa: E731
	slab = inspect(task("Concrete frame"), "Hold", -9, "Level 2 slab, bays A-D, before the pour",
	               {"Reinforcement cover (mm)": ["45", "42", "47"], "Formwork line and level (mm)": ["2", "-3"],
	                "Embedded items in place": "Yes", "Formwork clean and release agent applied": "Yes"},
	               verified_by="Ir. Jean Bolamba (client's engineer)", remarks="Pour released at 14:00.")
	tiles = inspect(task("Floor tiling, ground floor"), "Surveillance", -8, "Ground floor, zone 4 (corridor)",
	                {"Hollow tiles on tap test": "6 tiles", "Lippage (mm)": ["0.5", "1"], "Joint width (mm)": ["3", "3"]},
	                remarks="Six tiles hollow along the corridor wall: adhesive coverage under 80%.")
	wall = inspect(task("Blockwork"), "Witness", -3, "Level 1, grid C1-C4",
	               {"Plumb deviation per storey (mm)": ["12", "4"], "Line deviation over 5 m (mm)": ["3", "4"],
	                "Mortar joint thickness (mm)": ["10", "11"], "Wall ties installed": "Yes"},
	               verified_by="Ir. Jean Bolamba (client's engineer)", remarks="Wall at C3 out of plumb; to be taken down to course 6.")
	pending = inspect(task("Concrete frame"), "Hold", 0, "Level 3 columns C1-C8, before the pour", None)
	with as_user("pm"):
		ncr(tiles, root_cause="Adhesive applied in dabs instead of a full bed; the tiler was new to the gang.",
		    corrective="Six tiles lifted and relaid on a full adhesive bed; gang briefed on back-buttering.",
		    preventive="Tap test on every 20 m² before grouting.", owner=emp("Jean-Pierre", "Mukendi"), due=-2, cost=1150,
		    status="Action Taken")
		ncr(wall, root_cause="Gauge rod not used after the lunch break; the course lines drifted.",
		    owner=emp("Papy", "Tshilombo"), due=2, cost=640, status="Open")
		closed = insert({"doctype": "Non Conformance", "subject": "Honeycombing at column C4, level 1", "status": "Closed",
		                 "project": p, "wbs": "MSS-W-ES", "task": task("Concrete frame"), "raised_on": add_days(today(), -40),
		                 "details": "Honeycombing over 300 mm at the base of C4 after striking.",
		                 "root_cause": "Poor vibration at a congested lap; the poker could not reach the base.",
		                 "corrective_action": "Broken out to sound concrete and recast with repair mortar; the engineer approved.",
		                 "preventive_action": "Smaller poker for congested columns; pour in two lifts.",
		                 "action_owner": emp("Didier", "Kasongo"), "due_date": add_days(today(), -30), "cost_impact": 2400})
		frappe.db.set_value("Non Conformance", closed.name, "closed_on", add_days(today(), -25), update_modified=False)
		for name, offset in ((closed.name, -40),):
			frappe.db.set_value("Non Conformance", name, "creation", at(offset, 15), update_modified=False)
	log(f"Quality: {slab} accepted, {tiles} and {wall} rejected (NCRs raised), {pending} requested; NCR {closed.name} closed")


def masters():
	for checklist, params in CHECKLISTS.items():
		for name, *_ in params:
			if not frappe.db.exists("Quality Inspection Parameter", name):
				insert({"doctype": "Quality Inspection Parameter", "parameter": name})
		if not frappe.db.exists("Quality Inspection Template", checklist):
			insert({"doctype": "Quality Inspection Template", "quality_inspection_template_name": checklist,
			        "item_quality_inspection_parameter": [
			            {"specification": n, "numeric": num, "min_value": lo, "max_value": hi, "value": val}
			            for n, num, lo, hi, val in params]})
	for ttype, checklist in TYPES.items():
		if not frappe.db.exists("Task Type", ttype):
			insert({"doctype": "Task Type", "name": ttype, "__newname": ttype, "description": f"{ttype}: inspected with the {checklist} checklist"})
		frappe.db.set_value("Task Type", ttype, "quality_inspection_template", checklist)


def inspect(task, point, offset, where, readings, verified_by=None, remarks=None):
	from a3_constructa.overrides.quality import request_inspection

	with as_user("requester"):
		name = request_inspection(task, point, add_days(today(), offset), inspected_by=user("requester"))
		qi = frappe.get_doc("Quality Inspection", name)
		qi.description = f"{frappe.db.get_value('Task', task, 'subject')}: {where}"
		qi.verified_by, qi.remarks = verified_by, remarks
		if readings:
			for r in qi.readings:
				got = readings[r.specification]
				if isinstance(got, list):
					for i, v in enumerate(got, 1):
						r.set(f"reading_{i}", v)
				else:
					r.reading_value = got
			qi.flags.ignore_permissions = True
			qi.save()
			qi.submit()
		else:
			qi.flags.ignore_permissions = True
			qi.save()
	frappe.db.set_value("Quality Inspection", name, "creation", at(offset, 9), update_modified=False)
	return name


def ncr(qi, root_cause, owner, due, cost, status, corrective=None, preventive=None):
	name = frappe.db.get_value("Quality Inspection", qi, "non_conformance")
	nc = frappe.get_doc("Non Conformance", name)
	nc.update({"root_cause": root_cause, "action_owner": owner, "due_date": add_days(nc.raised_on, 0) if due is None else add_days(today(), due),
	           "cost_impact": cost, "corrective_action": corrective, "preventive_action": preventive, "status": status})
	nc.flags.ignore_permissions = True
	nc.save()
	frappe.db.set_value("Non Conformance", name, "creation", at((frappe.utils.getdate(nc.raised_on) - frappe.utils.getdate(today())).days, 16),
	                    update_modified=False)
	if status == "Action Taken":
		comment("Non Conformance", name, "Relaid on Monday; re-inspection booked with the client's engineer.", "requester", at(-1, 15))
