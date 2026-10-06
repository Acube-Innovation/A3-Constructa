# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-03: one case for each check on the Contracts & Awards overview, and a programme
for the hospital so its first milestones fall in the next 30 days.

- Milestones past their planned end: the Administrative Centre's frame (already late).
- Deliverables past their due date: the overdue submittal from the planning stage.
- Variation orders unanswered after 30 days: extra site hoarding, with the client for 38 days.
- Change events unpriced after 14 days: a cracked slab at the link bridge, logged 20 days ago.
- Awards not handed over: emergency roof repairs at the Provincial Assembly, awarded directly.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, as_user, at, comment, day, log

EMERGENCY = "Provincial Assembly: emergency roof leak repairs"
# (milestone, start day, end day, weightage, billing %)
HOSPITAL_PROGRAMME = [
	("Advance payment guarantee and insurances lodged", 0, 20, 0, 15),
	("Site possession from the hospital board", 27, 27, 0, 0),
	("Mobilisation and site set-up", 27, 60, 5, 5),
	("Substructure", 60, 180, 20, 20),
	("Frame and envelope", 150, 330, 30, 25),
	("Finishes and theatre fit-out", 300, 480, 25, 20),
	("MEP, commissioning and handover", 420, 567, 20, 15),
]


def run():
	if frappe.db.exists("Awarded Quotation", {"title": EMERGENCY}):
		log("contracts overview cases already present")
		return
	made = [hospital_programme(), unanswered_vo(), unpriced_change(), direct_award()]
	log("Contracts overview cases: " + "; ".join(m for m in made if m))


def hospital_programme():
	award = frappe.db.get_value("Awarded Quotation", {"title": ["like", "Hospital extension%"]}, "name")
	if not award or frappe.db.exists("Awarded Quotation Milestone", {"parent": award}):
		return None
	with as_user("pm"):
		a = frappe.get_doc("Awarded Quotation", award)
		for name, start, end, weight, billing in HOSPITAL_PROGRAMME:
			a.append("milestones", {"milestone": name, "planned_start": day(start), "planned_end": day(end),
			                        "weightage": weight, "billing_percent": billing, "status": "Not Started"})
		a.flags.ignore_permissions = True
		a.save()
	return f"{award}: {len(HOSPITAL_PROGRAMME)} milestones"


def main_award():
	return frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "status": "In Progress"}, "name", order_by="creation asc")


def unanswered_vo():
	award = main_award()
	if not award:
		return None
	with as_user("qs"):
		vo = frappe.get_doc({"doctype": "Variation Order", "subject": "Extra site hoarding along Avenue de la Justice",
		                     "awarded_quotation": award, "vo_date": day(-40), "client_reference": "GPE/VO/009",
		                     "variation_type": "Addition", "status": "Draft", "time_extension_days": 0,
		                     "reason": "City asked for a continuous 2.4 m hoarding while the avenue is open to the public.",
		                     "items": [{"description": "Plywood hoarding 2.4 m, painted, 85 m", "wbs": "MSS-W", "qty": 85,
		                                "uom": "Meter", "rate": 40}]})
		vo.flags.ignore_permissions = True
		vo.insert()
		vo.status = "Submitted to Client"
		vo.save()
	frappe.db.set_value("Variation Order", vo.name, {"submitted_date": day(-38), "creation": at(-40, 10), "modified": at(-38, 15)},
	                    update_modified=False)
	comment("Variation Order", vo.name, "Sent to the client's engineer; no answer yet despite two reminders.", "pm", at(-10, 9))
	return f"{vo.name} with the client since {day(-38)}"


def unpriced_change():
	award = main_award()
	if not award:
		return None
	employee = frappe.db.get_value("Employee", {"user_id": frappe.db.get_value("User", {"first_name": "Patrick"}, "name")}, "name")
	with as_user("requester"):
		ce = frappe.get_doc({"doctype": "Change Event", "title": "Cracked existing slab at the link bridge", "awarded_quotation": award,
		                     "raised_on": day(-20), "raised_by": employee, "source": "Site condition", "wbs": "MSS-W-ES",
		                     "description": "Hairline cracks in the existing slab where the new link bridge bears. Engineer to inspect before pricing.",
		                     "status": "Open"})
		ce.flags.ignore_permissions = True
		ce.insert()
	frappe.db.set_value("Change Event", ce.name, {"creation": at(-20, 11), "modified": at(-20, 11)}, update_modified=False)
	return f"{ce.name} open since {day(-20)}"


def direct_award():
	with as_user("md"):
		a = frappe.get_doc({"doctype": "Awarded Quotation", "title": EMERGENCY, "customer": CUSTOMER, "company": COMPANY,
		                    "currency": "USD", "award_date": day(-3), "award_reference": "GPE/URG/2026/006", "status": "Awarded",
		                    "start_date": day(4), "end_date": day(34), "retention_percent": 5,
		                    "scope": "Emergency repairs to the roof membrane and rainwater outlets over the debating chamber, awarded directly.",
		                    "components": [{"component": "Roof leak repairs, lump sum", "qty": 1, "rate": 38_500, "uom": "Lump Sum"}]})
		a.flags.ignore_permissions = True
		a.insert()
	frappe.db.set_value("Awarded Quotation", a.name, {"creation": at(-3, 15), "modified": at(-3, 15)}, update_modified=False)
	comment("Awarded Quotation", a.name, "Direct award after the storm damage; mobilise within the week.", "md", at(-3, 15, 5))
	return f"{a.name} awarded, not handed over"
