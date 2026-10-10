# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-03B: variation orders through every status, moving the contract and the WBS budget.

- VO-0001 (entrance ramp and canopy): its lines go onto the WBS and it is approved.
- The fire-rated glazing from change event CE-0003 is sent and approved.
- An omission (feature-wall paint) is approved, so the painting budget falls.
- External floodlighting is rejected by the client.
- A second flag pole is approved, then cancelled when the client withdraws it:
  the budget goes up and comes back down.
- Extra sockets in the archive room are still a draft; the R11 tiles stay with the client.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, log, user

# (subject, type, [(description, wbs, qty, uom, rate)], days, raised day, [(status, day)], note)
NEW = [
	("Omit feature-wall paint; client supplies wallpaper", "Omission",
	 [("Feature-wall emulsion omitted", "MSS-W-PT", -370, "Square Meter", 5.00)], 0, -24,
	 [("Submitted to Client", -22), ("Approved", -16)], "Client's interior designer supplies wallpaper for the lobby walls."),
	("External floodlighting to the car park", "Addition",
	 [("LED floodlights on 8 m columns, supply and install", "MSS-W-MEP", 8, "Nos", 800)], 4, -21,
	 [("Submitted to Client", -19), ("Rejected", -7)], "Client will light the car park under the city's street-lighting contract."),
	("Second flag pole at the entrance", "Addition",
	 [("Aluminium flag pole 9 m with base", "MSS-W-ES", 1, "Nos", 2300)], 2, -28,
	 [("Submitted to Client", -27), ("Approved", -18), ("Cancelled", -9)], "Approved, then withdrawn: protocol office supplies its own pole."),
	("Extra power sockets in the archive room", "Addition",
	 [("Twin socket outlets on dedicated circuit", "MSS-W-MEP", 10, "Nos", 110)], 0, -2, [], None),
]


def run():
	award = frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "status": "In Progress"}, "name", order_by="creation asc")
	if not award:
		log("no award in progress; run the planning stage first")
		return
	if frappe.db.exists("Variation Order", {"awarded_quotation": award, "subject": NEW[0][0]}):
		log("variation orders already through their statuses")
		return
	made = [ramp_and_canopy(award), glazing(award)]
	for subject, kind, lines, days, raised, moves, note in NEW:
		made.append(new_order(award, subject, kind, lines, days, raised, moves, note))
	before, after = frappe.db.get_value("Awarded Quotation", award, ["contract_value", "revised_contract_value"])
	log("Variations: " + "; ".join(made) + f". Contract ${before:,.0f} → ${after:,.0f}")


def move(name, status, on, by="pm"):
	with as_user(by):
		vo = frappe.get_doc("Variation Order", name)
		vo.status = status
		if status == "Approved":
			vo.approved_date = day(on)
		vo.flags.ignore_permissions = True
		vo.save()
	dates = {"modified": at(on, 15)}
	if status == "Submitted to Client":
		dates["submitted_date"] = day(on)
	frappe.db.set_value("Variation Order", name, dates, update_modified=False)
	# The budget moved on the story day, not today.
	frappe.db.sql("""update `tabBudget Revision Log` set posted_on = %s
		where reference_doctype = 'Variation Order' and reference_name = %s and posted_on > %s""", (at(on, 15), name, at(on, 15)))


def ramp_and_canopy(award):
	"""The first variation: its lines go onto the WBS, then it is approved (or was already)."""
	name = frappe.db.get_value("Variation Order", {"awarded_quotation": award, "client_reference": "GPE/VO/004"}, "name")
	if not name:
		return None
	with as_user("qs"):
		vo = frappe.get_doc("Variation Order", name)
		for row in vo.items:
			row.wbs = row.wbs or ("MSS-W-FL" if row.cost_head == "MSS-AR-FL" else "MSS-W-ES")
		vo.flags.ignore_permissions = True
		vo.save()
	frappe.db.set_value("Variation Order", name, "submitted_date", day(-58), update_modified=False)
	if vo.status != "Approved":
		move(name, "Approved", -52)
	else:
		frappe.db.sql("""update `tabBudget Revision Log` set posted_on = %s
			where reference_doctype = 'Variation Order' and reference_name = %s""", (at(-52, 15), name))
	frappe.db.set_value("Variation Order", name, {"approved_date": day(-52), "approved_by": user("pm")}, update_modified=False)
	# The R11 tiles went to the client when they were raised.
	pending = frappe.db.get_value("Variation Order", {"awarded_quotation": award, "client_reference": "GPE/VO/007"}, ["name", "vo_date"], as_dict=True)
	if pending:
		frappe.db.set_value("Variation Order", pending.name, "submitted_date", pending.vo_date, update_modified=False)
	return f"{name} on WBS, approved"


def glazing(award):
	ce = frappe.db.get_value("Change Event", {"awarded_quotation": award, "variation_order": ["is", "set"]}, ["name", "variation_order"], as_dict=True)
	if not ce:
		return None
	frappe.db.set_value("Variation Order", ce.variation_order, "change_event", ce.name, update_modified=False)
	move(ce.variation_order, "Submitted to Client", -10)
	move(ce.variation_order, "Approved", -4)
	comment("Variation Order", ce.variation_order, "Signed by the client's representative on site.", "pm", at(-4, 16))
	return f"{ce.variation_order} (from {ce.name}) approved"


def new_order(award, subject, kind, lines, days, raised, moves, note):
	with as_user("qs"):
		vo = frappe.get_doc({"doctype": "Variation Order", "subject": subject, "awarded_quotation": award, "vo_date": day(raised),
		                     "variation_type": kind, "status": "Draft", "time_extension_days": days, "reason": note,
		                     "items": [{"description": d, "wbs": w, "qty": q, "uom": u, "rate": r} for d, w, q, u, r in lines]})
		vo.flags.ignore_permissions = True
		vo.insert()
	frappe.db.set_value("Variation Order", vo.name, {"creation": at(raised, 10), "modified": at(raised, 10)}, update_modified=False)
	for status, on in moves:
		move(vo.name, status, on)
	if note and moves:
		comment("Variation Order", vo.name, note, "pm", at(moves[-1][1], 16))
	return f"{vo.name} {moves[-1][0] if moves else 'Draft'}"
