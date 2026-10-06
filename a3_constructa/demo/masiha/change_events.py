# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-03A: change events on the Administrative Centre, one in every status.

- Open: rock in the lift pit, logged by the site engineer, not priced yet.
- Priced: the client wants a second server room; priced, waiting for a decision.
- Became VO: fire-rated lobby glazing, priced and turned into a draft variation order.
- Absorbed: an RFI answer on skirting height, within our rates.
- Claim: the city closed the access road for six days; a delay claim, not a variation.
- Closed: the client asked to move a door, then withdrew it.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, log

# (key, title, source, wbs, rough cost, rough days, raised by, day, status, note)
EVENTS = [
	("rock", "Rock in the lift pit at grid C4", "Site condition", "MSS-W-ES", 6_500, 4, "requester", -3, "Open", None),
	("server", "Second server room with raised floor", "Client instruction", "MSS-W-MEP", 18_400, 10, "pm", -12, "Priced", None),
	("glazing", "Fire-rated glazing to the lobby screens", "Design change", "MSS-W-DW", 9_200, 5, "pm", -20, "Priced", None),
	("skirting", "RFI-012: skirting height 100 mm", "RFI answer", "MSS-W-FL-A", 350, 0, "requester", -26, "Absorbed",
	 "Within our tiling rates; no change to the price."),
	("road", "City closed the access road for six days", "Site condition", "MSS-W", 7_800, 6, "pm", -34, "Claim",
	 "Not a change to the works: notice of delay and standing time sent to the client."),
	("door", "Move the meeting-room door 1.2 m east", "Client instruction", "MSS-W-DW", 600, 1, "pm", -40, "Closed",
	 "Withdrawn by the client the next day."),
]
DESCRIPTIONS = {
	"rock": "Excavation for the lift pit hit rock at 1.4 m below formation, grid C4. Breaker needed; extra disposal.",
	"server": "Client's IT department wants a second server room on level 1 with a raised floor, extra cooling and two dedicated circuits.",
	"glazing": "Fire consultant's revision C: lobby screens to be EI30 fire-rated glazing instead of standard toughened glass.",
	"skirting": "RFI-012 asked the skirting height in the offices. Architect answered 100 mm porcelain, as tiled.",
	"road": "Mbandaka city closed Avenue de la Justice for drainage works; no deliveries could reach site for six working days.",
	"door": "Client asked to move the meeting-room door to suit the furniture layout.",
}


def run():
	award = frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "status": "In Progress"}, "name", order_by="creation asc")
	if not award:
		log("no award in progress; run the planning stage first")
		return
	if frappe.db.exists("Change Event", {"awarded_quotation": award}):
		log("change events already present")
		return
	from a3_constructa.a3_constructa.doctype.change_event.change_event import make_variation_order

	employees = {k: frappe.db.get_value("Employee", {"user_id": frappe.db.get_value("User", {"first_name": f}, "name")}, "name")
	             for k, f in (("requester", "Patrick"), ("pm", "Didier"))}
	made = []
	for key, title, source, wbs, cost, days, by, on, status, note in EVENTS:
		with as_user(by):
			ce = frappe.get_doc({"doctype": "Change Event", "title": title, "awarded_quotation": award, "raised_on": day(on),
			                     "raised_by": employees[by], "source": source, "description": DESCRIPTIONS[key], "wbs": wbs,
			                     "status": "Open"})
			if status != "Open":  # the rock is logged from site, not priced yet
				ce.update({"rough_cost": cost, "rough_days": days})
			ce.flags.ignore_permissions = True
			ce.insert()
		frappe.db.set_value("Change Event", ce.name, {"creation": at(on, 10), "modified": at(on, 10)}, update_modified=False)
		if status == "Open":
			made.append(f"{ce.name} Open")
			continue
		with as_user("qs"):
			ce = frappe.get_doc("Change Event", ce.name)
			ce.status = "Priced"
			ce.flags.ignore_permissions = True
			ce.save()
		if key == "glazing":
			with as_user("pm"):
				vo = make_variation_order(ce.name)
			frappe.db.set_value("Variation Order", vo, {"vo_date": day(on + 6), "creation": at(on + 6, 14), "modified": at(on + 6, 14)},
			                    update_modified=False)
			comment("Change Event", ce.name, f"Client agreed it is a variation; {vo} drafted for their signature.", "pm", at(on + 6, 15))
			made.append(f"{ce.name} → {vo}")
			continue
		if status != "Priced":
			with as_user("pm"):
				ce = frappe.get_doc("Change Event", ce.name)
				ce.update({"status": status, "decision_note": note})
				ce.flags.ignore_permissions = True
				ce.save()
		made.append(f"{ce.name} {status}")
	comment("Awarded Quotation", award, "Change log started: six change events so far, see the Change Event Register.", "pm", at(-1, 17))
	log("Change events: " + "; ".join(made))
