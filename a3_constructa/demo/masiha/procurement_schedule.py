# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-05A: procurement plans that follow the programme.

Lead times on the items: cement 21 days (local mill), Y16 rebar 75 days
(imported through Matadi).

- Hospital extension: the plan is refreshed from the schedule - cement for the
  substructure (required 7 days before it starts, PR due in a month) and rebar
  for the foundations, whose PR date has already passed with nothing requested:
  flagged. The crane is a Hire line, already on order, so not flagged.
- Committee wing: refreshed - cement for the floor screed; its PR date passed
  last month: flagged (the look-ahead shows it short too).
"""

import frappe
from frappe.utils import add_days, today

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, log

LEAD_TIMES = {"CEM-425-50": 21, "STL-Y16": 75}


def run():
	for item, days in LEAD_TIMES.items():
		frappe.db.set_value("Item", item, "lead_time_days", days, update_modified=False)
	hospital = frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"], "company": COMPANY}, "name")
	wing = frappe.db.get_value("Project", {"project_name": "Provincial Assembly committee wing", "company": COMPANY}, "name")
	if frappe.db.exists("Procurement Plan", {"project": hospital}):
		log("schedule-driven plans already present")
		return
	made = []
	for project, extra in ((hospital, [{"item_code": "EQ-CRANE-HIRE", "procurement_route": "Hire", "wbs": "HGR-W-ES", "anticipated_qty": 10,
	                                    "uom": "Day", "required_on_site_date": add_days(today(), 4), "lead_time_days": 14,
	                                    "remarks": "Mobile crane with operator, for the frame (hire order placed)."}]),
	                       (wing, [])):
		with as_user("pm"):
			plan = frappe.get_doc({"doctype": "Procurement Plan", "project": project, "plan_date": add_days(today(), -2), "status": "Submitted",
			                       "items": extra})
			plan.flags.ignore_permissions = True
			plan.insert()
			plan.reload()
			plan.flags.ignore_permissions = True
			r = plan.refresh_from_schedule()
		frappe.db.set_value("Procurement Plan", plan.name, "creation", at(-2, 10), update_modified=False)
		plan.reload()
		made.append(f"{plan.name} {project}: {r['added']} from the schedule, {sum(x.pr_overdue for x in plan.items)} overdue")
	comment("Procurement Plan", frappe.db.get_value("Procurement Plan", {"project": hospital}),
	        "Rebar PR is late: the import takes 75 days. Raise it this week or re-sequence the foundations.", "procurement", at(-1, 11))
	log("Procurement plans: " + "; ".join(made))
