# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06D: progress measured on the Administrative Centre.

Weekly measurements since each task started: earthworks complete (4,200 m³), the
frame at 945 of 1,350 m³ (70%), blockwork at 910 of 2,600 m² (35%), ground-floor
tiling at 360 of 600 m² (60%); the work not started is measured by quantity too.
Doors and windows follows its weighted sub-tasks. Site establishment is manual.
"""

import frappe
from frappe.utils import add_days, getdate, today

from a3_constructa.demo.masiha.common import as_user, log, project

# subject: (method, total done, measurement every n days)
MEASURED = {
	"Earthworks and substructure": ("Quantity", 4200, 7),
	"Concrete frame": ("Quantity", 945, 7),
	"Blockwork": ("Quantity", 910, 7),
	"Floor tiling, ground floor": ("Quantity", 360, 7),
	"Roof structure and covering": ("Quantity", 0, 0),
	"MEP first fix": ("Manual", 0, 0),
	"Doors and windows": ("Sub-tasks", 0, 0),
	"Finishes and handover": ("Manual", 0, 0),
	"Testing, commissioning and handover": ("Manual", 0, 0),
	"Site establishment": ("Manual", 0, 0),
}
SHEETS = {"Concrete frame": "Pour record", "Blockwork": "Block count", "Floor tiling, ground floor": "Tiling measure",
          "Earthworks and substructure": "Survey"}


def run():
	p = project()
	if frappe.db.exists("Task Progress Log", {"parenttype": "Task"}):
		log("progress logs already present")
		return
	frappe.flags.a3_task_cascade = 1
	frappe.flags.a3_no_reschedule = 1
	made = []
	try:
		with as_user("pm"):
			for subject, (method, total, every) in MEASURED.items():
				name = frappe.db.get_value("Task", {"project": p, "subject": subject})
				t = frappe.get_doc("Task", name)
				t.progress_method = method
				if total:
					t.set("progress_log", entries(t, total, every, SHEETS.get(subject, "Measure")))
				t.flags.ignore_permissions = True
				t.save()
				made.append(f"{subject} {t.progress:g}%")
	finally:
		frappe.flags.a3_task_cascade = 0
		frappe.flags.a3_no_reschedule = 0
	from a3_constructa.overrides.task_progress import update_wbs_progress

	update_wbs_progress(p)
	log("Progress: " + "; ".join(made) + f"; WBS {frappe.db.get_value('WBS', 'MSS-W', 'progress_percent')}% overall")


def entries(task, total, every, sheet):
	"""Weekly measurements from the task's start to its end, or to yesterday if still running."""
	start = getdate(task.exp_start_date)
	stop = getdate(task.completed_on or task.exp_end_date) if task.status == "Completed" else getdate(add_days(today(), -1))
	dates = []
	d = add_days(start, every - 1)
	while getdate(d) <= stop:
		dates.append(getdate(d))
		d = add_days(d, every)
	if not dates or dates[-1] != stop:
		dates.append(stop)
	# A slow first week, then a steady rate.
	weights = [0.5] + [1.0] * (len(dates) - 1)
	share = total / sum(weights)
	rows, left = [], total
	for i, (when, w) in enumerate(zip(dates, weights)):
		qty = round(share * w) if i < len(dates) - 1 else left
		left -= qty
		rows.append({"date": when, "qty_done": qty, "source": "Manual", "reference": f"{sheet} {i + 1:02d}"})
	return rows
