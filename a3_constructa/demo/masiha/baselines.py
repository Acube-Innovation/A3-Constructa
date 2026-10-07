# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06C: baselines and schedule revisions.

Administrative Centre: revision 0 is the programme agreed at award (frozen 150 days
ago). Since then the earthworks finished 8 days late, the frame slipped 21 days
(rain and a rebar shortage), and the work after it 5 to 15 days; testing and
commissioning was compressed so the handover date holds. Revision 1, the recovery
programme that re-baselines today's dates, is a draft waiting for the client.
Hospital: revision 0, frozen when its programme was set; nothing has moved yet.
"""

import frappe
from frappe.utils import add_days, getdate

from a3_constructa.demo.masiha.common import as_user, at, comment, day, log, project

# subject: (days the start slipped, days the end slipped) since the programme at award
SLIPS = {
	"Earthworks and substructure": (0, 8),
	"Concrete frame": (8, 21),
	"Blockwork": (10, 10),
	"Floor tiling, ground floor": (5, 5),
	"Roof structure and covering": (15, 15),
	"MEP first fix": (15, 15),
	"Doors and windows": (10, 10),
	"Door frames and doors": (10, 10),
	"Windows and glazing": (10, 10),
	"Ironmongery and adjustments": (10, 10),
	"Finishes and handover": (15, 15),
	"Testing, commissioning and handover": (15, 0),
}


def run():
	p = project()
	if frappe.db.exists("Schedule Revision", {"project": p}):
		log("schedule revisions already present")
		return
	from a3_constructa.overrides.task import critical_path
	from a3_constructa.overrides.task_baseline import set_variance

	tasks = frappe.get_all("Task", filters={"project": p, "is_template": 0}, fields=["name", "subject", "exp_start_date", "exp_end_date", "completed_on"])
	current = {t.name: (t.exp_start_date, t.exp_end_date) for t in tasks}
	# Put the programme back as it was at award, freeze it, then bring today's dates back.
	for t in tasks:
		ds, de = SLIPS.get(t.subject, (0, 0))
		frappe.db.set_value("Task", t.name, {"exp_start_date": add_days(t.exp_start_date, -ds), "exp_end_date": add_days(t.exp_end_date, -de)},
		                    update_modified=False)
	rev0 = revision(p, "Programme agreed with the client at award: the contract baseline.", -150)
	for name, (start, end) in current.items():
		frappe.db.set_value("Task", name, {"exp_start_date": start, "exp_end_date": end}, update_modified=False)
		set_variance(frappe.get_doc("Task", name), save=True)
	critical_path(p)
	with as_user("pm"):
		rev1 = frappe.get_doc({"doctype": "Schedule Revision", "project": p, "revision_date": day(0), "variation_order": "VO-2026-0003",
		                       "reason": "Recovery programme after the frame delay (rain, rebar shortage) and the lobby extension in VO-2026-0003; "
		                                 "testing compressed so the handover holds. Sent to the client for approval."})
		rev1.flags.ignore_permissions = True
		rev1.insert()
	comment("Schedule Revision", rev1.name, "Client's engineer has the recovery programme; meeting on Friday.", "pm", at(0, 15))
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")
	rev_h = revision(hospital, "Programme at handover from the award: the contract baseline.", -2)
	log(f"Baselines: {rev0} (revision 0, Administrative Centre), {rev1.name} draft revision 1; {rev_h} (hospital revision 0)")


def revision(project_name, reason, when):
	with as_user("pm"):
		r = frappe.get_doc({"doctype": "Schedule Revision", "project": project_name, "revision_date": day(when), "reason": reason})
		r.flags.ignore_permissions = True
		r.insert()
		r.submit()
	frappe.db.set_value("Schedule Revision", r.name, {"creation": at(when, 10), "modified": at(when, 16)}, update_modified=False)
	return r.name
