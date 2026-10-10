# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-13E: the crews' hours and attendance behind their September progress.

The blockwork and ground-floor tiling progress logs (P-06D) had no hours behind
them before the site reports started on 5 October. Here are the gangs' weekly
timesheets (Monday to Saturday, split over the active members) and their
attendance on the Administrative Centre, for the five weeks from 31 August:

- Blockwork gang on Blockwork (WBS Architectural works): steady at first, then
  slowing - 370 hours for the same 165 m² in the last week of September,
  a productivity factor of 0.81 against the gang's standard 22 m² a day;
- Tiling gang A on the ground-floor tiling (WBS A): slow in its first week while
  it learned the job (0.83), then on standard;
- the general labour pool on site every day, with no labour planned for it on
  the programme (it shows on the histogram as unplanned).
"""

import frappe
from frappe.utils import add_days, flt, getdate

from a3_constructa.a3_constructa.doctype.crew.crew import split_crew_hours
from a3_constructa.demo.masiha.common import COMPANY, exists, log, project

MARK = "P-13E crew week"
# crew, task, week (Monday), crew hours in the week
WEEKS = [
	("CRW-0002", "TASK-2026-00004", "2026-08-31", 160), ("CRW-0002", "TASK-2026-00004", "2026-09-07", 290),
	("CRW-0002", "TASK-2026-00004", "2026-09-14", 310), ("CRW-0002", "TASK-2026-00004", "2026-09-21", 340),
	("CRW-0002", "TASK-2026-00004", "2026-09-28", 370),
	("CRW-0001", "TASK-2026-00005", "2026-09-07", 64), ("CRW-0001", "TASK-2026-00005", "2026-09-14", 112),
	("CRW-0001", "TASK-2026-00005", "2026-09-21", 104), ("CRW-0001", "TASK-2026-00005", "2026-09-28", 120),
]
# (crews, first day, last day): September for the three gangs; then the days the
# site reports cover (5-6 October), when the tilers were a subcontractor's.
ATTENDANCE = [(("CRW-0002", "CRW-0001", "CRW-0005"), "2026-08-31", "2026-10-03"), (("CRW-0002", "CRW-0005"), "2026-10-05", "2026-10-06")]


def run():
	p = project()
	made = 0
	for crew, task, monday, hours in WEEKS:
		note = f"{MARK} {crew} {monday}"
		if exists("Timesheet", {"note": note, "docstatus": 1}):
			continue
		t = frappe.db.get_value("Task", task, ["wbs"], as_dict=True)
		cost_code = frappe.db.get_value("Cost Code", {"wbs": t.wbs}, "name")
		members = [m for m in frappe.get_doc("Crew", crew).members if m.is_active]
		each = flt(hours / (len(members) * 6), 2)
		logs = {}
		for d in range(6):
			for line in split_crew_hours(crew, add_days(monday, d), each, project=p, task=task, wbs=t.wbs, cost_code=cost_code):
				emp = line.pop("employee")
				for k in ("employee_name", "role", "crew"):
					line.pop(k, None)
				logs.setdefault(emp, []).append(line)
		for emp, lines in logs.items():
			ts = frappe.get_doc({"doctype": "Timesheet", "company": COMPANY, "employee": emp, "parent_project": p, "note": note,
			                     "time_logs": lines})
			ts.flags.ignore_permissions = True
			ts.insert()
			ts.submit()
		made += 1
	log(f"crew weeks booked now: {made} of {len(WEEKS)} (blockwork 5 weeks, tiling 4)")
	attendance(p)


def attendance(p):
	site = frappe.db.get_value("Project", p, "location") if frappe.get_meta("Project").has_field("location") else None
	marked, workers = 0, set()
	for crews, first, last in ATTENDANCE:
		employees = {m.employee for c in crews for m in frappe.get_doc("Crew", c).members if m.is_active}
		workers |= employees
		# A worker added to a crew later in the story (D-R's new site helper) has no
		# attendance before joining, and HRMS refuses it; a re-run would otherwise fail.
		joined = {e: getdate(frappe.db.get_value("Employee", e, "date_of_joining")) for e in employees}
		day = getdate(first)
		while day <= getdate(last):
			if day.weekday() < 6:  # Monday to Saturday
				for emp in employees:
					if day < joined[emp] or frappe.db.exists("Attendance", {"employee": emp, "attendance_date": day, "docstatus": ["<", 2]}):
						continue
					a = frappe.get_doc({"doctype": "Attendance", "employee": emp, "attendance_date": day, "status": "Present",
					                    "company": COMPANY, "project": p, "site": site})
					a.flags.ignore_permissions = True
					a.insert()
					a.submit()
					marked += 1
			day = add_days(day, 1)
	log(f"attendance marked now: {marked} worker-days for {len(workers)} workers (31 Aug - 3 Oct, 5-6 Oct)")
