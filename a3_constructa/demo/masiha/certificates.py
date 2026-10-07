# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-07B: skills, certificates and their expiry.

HR is Josée Mputu (HR officer). The excavator needs a licensed operator (Heavy
Equipment requires an operator licence):
- Patrice Ekofo's operator licence expires in 5 days: HR and his manager (the PM)
  have had the 7-day reminder;
- Jean-Pierre Mukendi's first-aid ticket expires in 25 days: HR has had the
  30-day reminder;
- a steel fixer's welding ticket lapsed 10 days ago, a mason's work-at-height
  ticket 12 days ago; another welder's runs out in 45 days.
Trade tests (no expiry) on the tilers and masons; skill maps for the operator, the
tiling foreman and a mason. A new helper, Samuel Bompeka, starts next week: his
onboarding (draft) follows the "Site worker" template.
"""

import frappe
from frappe.utils import add_days, add_years, today

from a3_constructa.demo.masiha.common import COMPANY, DEMO_PASSWORD, at, comment, insert, log

HR = ("Josée", "Mputu", "josee.mputu@masiha.demo")
# (first, last): [(type, no, issued by, issued (days), expires (days or None))]
CERTS = {
	("Patrice", "Ekofo"): [("Operator licence", "OPL-2023-0418", "Office National de l'Emploi - Kinshasa", -3 * 365 + 5, 5),
	                       ("First aid", "FA-2025-1102", "Croix-Rouge RDC", -140, 590)],
	("Jean-Pierre", "Mukendi"): [("First aid", "FA-2024-0877", "Croix-Rouge RDC", -705, 25), ("Trade test", "TT-TIL-0312", "INPP Mbandaka", -900, None)],
	("Alain", "Bokele"): [("Trade test", "TT-TIL-0455", "INPP Mbandaka", -600, None)],
	("Fiston", "Ngoy"): [("Trade test", "TT-TIL-0456", "INPP Mbandaka", -600, None)],
	("Junior", "Kalonji"): [("Trade test", "TT-MAS-0210", "INPP Mbandaka", -1000, None), ("Work at height", "WAH-2025-033", "Masiha HSE", -377, -12)],
	("Gloire", "Mbuyi"): [("Trade test", "TT-MAS-0388", "INPP Mbandaka", -400, None)],
	("Papy", "Tshilombo"): [("First aid", "FA-2026-0120", "Croix-Rouge RDC", -65, 300), ("Scaffolding", "SCF-2025-014", "Masiha HSE", -310, 55)],
	("Trésor", "Mavinga"): [("Welding", "WLD-2024-0090", "INPP Kinshasa", -685, 45)],
	("Blaise", "Kitenge"): [("Welding", "WLD-2024-0101", "INPP Kinshasa", -740, -10)],
}
SKILLS = {("Patrice", "Ekofo"): [("Excavator operation", 0.8)], ("Jean-Pierre", "Mukendi"): [("Tiling", 1.0), ("Setting out", 0.8)],
          ("Junior", "Kalonji"): [("Masonry", 0.8)]}


def emp(first, last):
	return frappe.db.get_value("Employee", {"first_name": first, "last_name": last, "company": COMPANY}, "name")


def run():
	frappe.db.set_value("Asset Category", "Heavy Equipment", "required_certificate", "Operator licence", update_modified=False)
	hr_officer()
	frappe.db.set_value("Employee", emp("Patrice", "Ekofo"), "reports_to", emp("Didier", "Kasongo"), update_modified=False)
	if frappe.db.exists("Employee Certificate", {"parenttype": "Employee"}):
		log("certificates already present")
		return
	for (first, last), rows in CERTS.items():
		e = frappe.get_doc("Employee", emp(first, last))
		for kind, no, by, issued, expires in rows:
			e.append("certificates", {"certificate_type": kind, "certificate_no": no, "issued_by": by, "issue_date": add_days(today(), issued),
			                          "expiry_date": add_days(today(), expires) if expires is not None else None})
		e.flags.ignore_permissions = True
		e.save()
	skills()
	onboarding()
	from a3_constructa.overrides.certificates import daily

	sent = daily()
	comment("Employee", emp("Patrice", "Ekofo"), "Licence renewal booked with ONEM for Thursday; until then he doesn't take the excavator.", "pm", at(0, 9))
	log(f"Certificates on {len(CERTS)} workers; reminders sent: " + "; ".join(f"{s['certificate']} ({s['days']} days) to {len(s['users'])}" for s in sent))


def hr_officer():
	first, last, email = HR
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "last_name": last, "send_welcome_email": 0,
		                    "user_type": "System User", "new_password": DEMO_PASSWORD,
		                    "roles": [{"role": r} for r in ("HR Manager", "HR User", "Employee")]})
		u.flags.ignore_permissions = True
		u.insert()
	if not frappe.db.exists("Employee", {"user_id": email}):
		if not frappe.db.exists("Designation", "HR Officer"):
			insert({"doctype": "Designation", "designation_name": "HR Officer"})
		insert({"doctype": "Employee", "first_name": first, "last_name": last, "gender": "Female", "company": COMPANY, "status": "Active",
		        "date_of_birth": "1988-06-14", "date_of_joining": add_days(today(), -400), "designation": "HR Officer", "user_id": email,
		        # HR works across every employee: no restriction to her own record.
		        "create_user_permission": 0})
	frappe.db.set_value("Employee", {"user_id": email}, "create_user_permission", 0, update_modified=False)
	for name in frappe.get_all("User Permission", filters={"user": email, "allow": "Employee"}, pluck="name"):
		frappe.delete_doc("User Permission", name, ignore_permissions=True)


def skills():
	for (first, last), rows in SKILLS.items():
		for skill, _p in rows:
			if not frappe.db.exists("Skill", skill):
				insert({"doctype": "Skill", "skill_name": skill})
		e = emp(first, last)
		if frappe.db.exists("Employee Skill Map", e):
			continue
		insert({"doctype": "Employee Skill Map", "employee": e,
		        "employee_skills": [{"skill": s, "proficiency": p, "evaluation_date": add_days(today(), -30)} for s, p in rows]})


def onboarding():
	if frappe.db.exists("Job Applicant", {"applicant_name": "Samuel Bompeka"}):
		return
	designation = "Site Helper"
	applicant = insert({"doctype": "Job Applicant", "applicant_name": "Samuel Bompeka", "email_id": "samuel.bompeka@example.cd",
	                    "status": "Accepted", "designation": designation})
	offer = insert({"doctype": "Job Offer", "job_applicant": applicant.name, "applicant_name": "Samuel Bompeka", "status": "Accepted",
	                "designation": designation, "offer_date": add_days(today(), -6), "company": COMPANY}, submit=True)
	template = frappe.db.get_value("Employee Onboarding Template", {"title": "Site worker"})
	doc = frappe.get_doc({"doctype": "Employee Onboarding", "job_applicant": applicant.name, "job_offer": offer.name,
	                      "employee_name": "Samuel Bompeka", "date_of_joining": add_days(today(), 6), "boarding_begins_on": add_days(today(), 1),
	                      "company": COMPANY, "designation": designation, "employee_onboarding_template": template})
	for a in frappe.get_doc("Employee Onboarding Template", template).activities:
		doc.append("activities", {k: a.get(k) for k in ("activity_name", "role", "user", "begin_on", "duration", "required_for_employee_creation")})
	doc.flags.ignore_permissions = True
	doc.insert()
