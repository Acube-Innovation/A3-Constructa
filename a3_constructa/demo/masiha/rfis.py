# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06J: the drawing register and RFIs.

- Administrative Centre drawings: the ground floor plan A-101 in revisions A, B
  and C (A and B superseded; rev C sent to site and to the tiling
  subcontractor, who hasn't acknowledged it yet), the level 1 slab
  reinforcement S-201, and the lobby lighting E-301 (for information).
  Hospital: the foundation layout S-001 and the theatre suite plan A-001.
- RFIs: the lobby threshold (answered, cost impact: its change event is
  absorbed within our rates; closed), a corridor paint colour (closed), beam B12
  against the MEP duct (open, 5 days overdue), archive room sockets (open, due in
  2 days); at the hospital, the lift pit depth (answered with a cost and time
  impact, change event not raised yet) and theatre ceiling clearance (open,
  2 days overdue).
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, at, day, log, project

HOSPITAL_SITE = "Mbandaka Hospital Site"
TILERS = "Equateur Tiling Works SARL"
ARCHITECT, STRUCTURAL, MEP = "Cabinet Ngoma Architectes (architect)", "Bureau d'études Kasaï (structural engineer)", "Elec-Fluides Congo (MEP consultant)"

# project key, drawing no, title, discipline, revision, days ago, status, [(issued to, days ago, acknowledged)]
DRAWINGS = [
	("admin", "A-101", "Ground floor plan", "Architectural", "A", -120, "For construction", [("Site", -119, 1)]),
	("admin", "A-101", "Ground floor plan", "Architectural", "B", -60, "For construction", [("Site", -59, 1), (TILERS, -58, 1)]),
	("admin", "S-201", "Level 1 slab reinforcement", "Structural", "0", -100, "For construction", [("Site", -99, 1), ("Steel fixers", -99, 1)]),
	("admin", "E-301", "Lobby lighting layout", "Electrical", "A", -20, "For information", []),
	("admin", "A-101", "Ground floor plan", "Architectural", "C", -14, "For construction", [("Site", -13, 1), (TILERS, -13, 0)]),
	("hospital", "S-001", "Foundation layout", "Structural", "1", -30, "For construction", [("Site", -29, 1)]),
	("hospital", "A-001", "Theatre suite plan", "Architectural", "P2", -10, "For information", []),
]

# project key, subject, question, addressed to, raised, required, drawing no, wbs,
#   answer, answered, cost impact, time impact, outcome (Closed / Answered / Open)
RFIS = [
	("admin", "Lobby floor level against the entrance threshold",
	 "Drawing A-101 rev B puts the lobby finished floor 20 mm below the entrance threshold. Raise the floor, or lower the threshold?",
	 ARCHITECT, -25, -18, "A-101", "MSS-W-FL",
	 "Raise the lobby floor 20 mm with screed to meet the threshold; see A-101 rev C.", -16, 1, 0, "Closed"),
	("admin", "Corridor paint colour",
	 "The finishes schedule gives no colour for the ground floor corridors.", ARCHITECT, -20, -13, "A-101", "MSS-W-PT",
	 "RAL 9010 pure white, matt, as the offices.", -14, 0, 0, "Closed"),
	("admin", "Beam B12 against the main supply duct",
	 "On S-201, beam B12 at gridline C is 600 mm deep; the MEP layout runs the 500 mm supply duct through the same zone. Can the beam be "
	 "penetrated, or does the duct move?", STRUCTURAL, -12, -5, "S-201", "MSS-W-ES", None, None, 0, 0, "Open"),
	("admin", "Socket heights in the archive room",
	 "E-301 doesn't give socket heights for the archive room shelving walls. 300 mm or above the shelving at 1,200 mm?", MEP, -6, 2,
	 "E-301", "MSS-W-MEP", None, None, 0, 0, "Open"),
	("hospital", "Lift pit depth",
	 "S-001 shows the lift pit 1.8 m deep; the lift supplier asks for 2.4 m. Which governs?", STRUCTURAL, -15, -10, "S-001", "HGR-W-ES",
	 "Use 2.4 m to the supplier's requirement; revised pit detail to follow.", -8, 1, 1, "Answered"),
	("hospital", "Ceiling clearance for theatre pendants",
	 "A-001 rev P2 shows a 2.7 m ceiling in theatre 1; the pendant supplier needs 3.0 m clear. Please confirm the ceiling height.",
	 ARCHITECT, -9, -2, "A-001", None, None, None, 0, 0, "Open"),
]


def run():
	if frappe.db.exists("Drawing Register", {"project": project()}):
		log("drawings and RFIs already present")
		return
	projects = {"admin": project(), "hospital": frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")}
	drawings = {}
	for key, no, title, discipline, rev, ago, status, sent in DRAWINGS:
		with as_user("requester"):
			d = frappe.get_doc({"doctype": "Drawing Register", "project": projects[key], "drawing_no": no, "title": title, "discipline": discipline,
			                    "revision": rev, "revision_date": day(ago), "status": status,
			                    "transmittals": [{"issued_to": to, "issued_on": day(on), "acknowledged": ack} for to, on, ack in sent]})
			d.flags.ignore_permissions = True
			d.insert()
		frappe.db.set_value("Drawing Register", d.name, "creation", at(ago, 9), update_modified=False)
		drawings[(key, no)] = d.name  # the latest revision registered wins
	made = []
	for key, subject, question, to, raised, required, no, wbs, answer, answered, cost, time, outcome in RFIS:
		with as_user("requester"):
			r = frappe.get_doc({"doctype": "RFI", "project": projects[key], "subject": subject, "question": question, "addressed_to": to,
			                    "raised_on": day(raised), "required_by": day(required), "drawing": drawings.get((key, no)), "wbs": wbs})
			r.flags.ignore_permissions = True
			r.insert()
			frappe.db.set_value("RFI", r.name, "creation", at(raised, 10), update_modified=False)
			if answer:
				r.reload()
				r.update({"answer": answer, "answered_on": day(answered), "cost_impact": cost, "time_impact": time})
				r.flags.ignore_permissions = True
				r.save()
		if outcome == "Closed":
			if cost or time:
				with as_user("pm"):
					from a3_constructa.a3_constructa.doctype.rfi.rfi import raise_change_event

					ce = frappe.get_doc("Change Event", raise_change_event(r.name))
					ce.update({"raised_on": day(answered), "rough_cost": 640, "status": "Absorbed",
					           "decision_note": "20 mm of screed over the 80 m² lobby: within our floor rates, absorbed."})
					ce.flags.ignore_permissions = True
					ce.save()
			with as_user("requester"):
				r.reload()
				r.status = "Closed"
				r.flags.ignore_permissions = True
				r.save()
		made.append(r.name)
	log(f"Drawings: {len(DRAWINGS)} revisions; RFIs: {', '.join(made)}")
