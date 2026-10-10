# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-06I: toolbox talks, permits to work and site incidents.

- Toolbox talks every Monday at the Administrative Centre for six weeks, led by
  the site engineer (one week missed, during the rain), with the crews and the
  tiling and painting subcontractors; two at the hospital with the steel fixers.
- Permits: hot work on the balustrade (closed), work at height on the blockwork
  scaffold (open, valid now), the hospital lift pit excavation (still open
  after its shift ended: expired), the crane lifting the stair flights
  (closed), an electrical isolation (cancelled), and hot work at the committee
  wing signed off by the PM.
- Incidents: a near miss (block off a scaffold), a tiler's cut finger (first
  aid), a steel fixer's twisted ankle in the lift pit 41 days ago (lost time,
  3 days), the crane clipping the hoarding (under investigation), and a diesel
  spill at the site tank (open).
"""

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime, today

from a3_constructa.demo.masiha.common import as_user, at, day, log, project
from a3_constructa.hse import PRECAUTIONS

TILERS, PAINTERS = "Equateur Tiling Works SARL", "Mbandaka Peinture et Finitions SARL"
HOSPITAL_SITE = "Mbandaka Hospital Site"


def run():
	if frappe.db.exists("Toolbox Talk", {"project": project()}):
		log("HSE records already present")
		return
	made = [talks(), permits(), incidents()]
	log("HSE: " + "; ".join(made))


def employee(first, last):
	return frappe.db.get_value("Employee", {"first_name": first, "last_name": last}, "name")


def crew_members(crew_name):
	crew = frappe.db.get_value("Crew", {"crew_name": crew_name}, "name")
	return frappe.get_all("Crew Member", filters={"parent": crew, "is_active": 1}, pluck="employee") if crew else []


def monday(weeks_ago):
	d = getdate(today())
	return add_days(d, -d.weekday() - 7 * weeks_ago)


def hospital():
	return frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")


def wing():
	return frappe.db.get_value("Project", {"project_name": ["like", "Provincial Assembly committee wing%"]}, "name")


# ---------------------------------------------------------------- toolbox talks
TOPICS = [
	(6, "Working at height: scaffold tags and harnesses",
	 "Green tag before use; harness clipped above shoulder height; report a missing toe board, don't fix it yourself."),
	(5, "Manual handling of blocks and cement bags",
	 "Two-person lift over 25 kg; bags from the pallet at waist height; use the barrow for more than 10 m."),
	(4, "Silica dust when cutting tiles: wet cutting and masks",
	 "Wet cutting only; FFP3 masks at the cutter; sweep wet, never dry."),
	# week 3 missed: rain stopped work on the Monday
	(2, "Hot work and the fire watch",
	 "No welding without a permit; extinguisher at the work point; fire watch stays an hour after."),
	(1, "Heat stress: water, shade and breaks",
	 "Water every 30 minutes; heavy work before 11:00; tell the foreman if dizzy."),
	(0, "Excavation edges and the lift pit barrier",
	 "Stay behind the rigid barrier; no spoil within 1 m of the edge; ladder access only."),
]
HOSPITAL_TOPICS = (
	(2, "Rebar cages: impalement caps and lifting", "Caps on every starter bar; cages lifted by the crane, not by hand."),
	(0, "Working near the crane: exclusion zones", "Stay out of the slew zone; the banksman alone signals the operator."),
)


def talks():
	engineer = employee("Patrick", "Lokwa")
	people = crew_members("Tiling gang A") + crew_members("Blockwork gang")
	made = 0
	for weeks_ago, topic, points in TOPICS:
		rows = [{"attendee_type": "Employee", "employee": e} for e in dict.fromkeys(people)]
		rows += [{"attendee_type": "Subcontractor", "supplier": TILERS, "headcount": 3}]
		if weeks_ago <= 2:
			rows.append({"attendee_type": "Subcontractor", "supplier": PAINTERS, "headcount": 4})
		talk(project(), monday(weeks_ago), topic, engineer, rows, points)
		made += 1
	fixers = crew_members("Steel fixers")
	for weeks_ago, topic, points in HOSPITAL_TOPICS:
		talk(hospital(), monday(weeks_ago), topic, employee("Moïse", "Kanku"), [{"attendee_type": "Employee", "employee": e} for e in fixers],
		     points)
		made += 1
	return f"{made} toolbox talks"


def site_of(project_name):
	"""The hospital project has no site of its own yet: its records name the hospital site."""
	return HOSPITAL_SITE if project_name == hospital() else None


def talk(project_name, date, topic, by, rows, points):
	with as_user("requester"):
		t = frappe.get_doc({"doctype": "Toolbox Talk", "project": project_name, "site": site_of(project_name), "talk_date": date, "topic": topic,
		                    "conducted_by": by, "attendees": rows, "key_points": points})
		t.flags.ignore_permissions = True
		t.insert()
	frappe.db.set_value("Toolbox Talk", t.name, {"creation": at((getdate(date) - getdate(today())).days, 7)}, update_modified=False)


# ---------------------------------------------------------------- permits
def permits():
	now = now_datetime()
	ekofo, tshilombo, mukendi, kanku = employee("Patrice", "Ekofo"), employee("Papy", "Tshilombo"), employee("Jean-Pierre", "Mukendi"), employee("Moïse", "Kanku")
	plan = [
		# project, wbs, type, work, from, hours, issued to, outcome, note
		(project(), "MSS-W-DW", "Hot work", "Welding the entrance balustrade posts", at(-9, 7), 9, tshilombo, "Closed",
		 "Welding finished 15:10; fire watch until 16:15, no hot spots."),
		(project(), "MSS-W-AR", "Work at height", "Blockwork to level 1, gridline C, from the tagged scaffold",
		 add_to_date(now, hours=-2), 10, tshilombo, "Open", None),
		(hospital(), "HGR-W-ES", "Excavation", "Lift pit excavation, 2.4 m deep", add_to_date(at(-1, 7), hours=0), 10, ekofo, "Open", None),
		(hospital(), "HGR-W-ES", "Lifting", "Crane lift of the precast stair flights", at(-6, 7), 9, kanku, "Closed",
		 "All four flights placed; exclusion zone lifted at 14:30."),
		(project(), "MSS-W-MEP", "Electrical isolation", "Isolate DB-2 for the first-fix tie-in", at(-2, 8), 8, mukendi, "Cancelled", None),
		(wing(), None, "Hot work", "Cutting the old roof steel brackets", at(-4, 8), 6, tshilombo, "Closed by PM",
		 "Brackets removed; area checked at 16:00."),
	]
	made = []
	for project_name, wbs, kind, work, start, hours, to, outcome, note in plan:
		if not project_name:
			continue
		with as_user("requester"):
			p = frappe.get_doc({"doctype": "Permit to Work", "project": project_name, "site": site_of(project_name), "wbs": wbs, "permit_type": kind, "work_description": work,
			                    "valid_from": start, "valid_to": add_to_date(get_datetime(start), hours=hours), "issued_to": to,
			                    "precautions": [{"precaution": x, "confirmed": 1} for x in PRECAUTIONS[kind]]})
			p.flags.ignore_permissions = True
			p.insert()
		frappe.db.set_value("Permit to Work", p.name, "creation", start, update_modified=False)
		if outcome in ("Closed", "Cancelled", "Closed by PM"):
			with as_user("pm" if outcome == "Closed by PM" else "requester"):
				p.reload()
				p.status = "Cancelled" if outcome == "Cancelled" else "Closed"
				p.closing_note = note or "MEP first fix postponed; isolation not needed."
				p.flags.ignore_permissions = True
				p.save()
			end = add_to_date(get_datetime(start), hours=hours - 0.5) if outcome != "Cancelled" else start
			frappe.db.set_value("Permit to Work", p.name, "closed_on", end, update_modified=False)
		made.append(p.name)
	return f"{len(made)} permits"


# ---------------------------------------------------------------- incidents
def incidents():
	mavinga = employee("Trésor", "Mavinga")
	plan = [
		dict(project=project(), occurred_on=at(-20, 10), incident_type="Near miss", severity="Medium", status="Closed",
		     description="A block fell from the level 1 scaffold at gridline C and landed inside the barricaded zone. Nobody was below.",
		     investigation="One lift had no toe board after the scaffold was extended.", root_cause="Toe board not refitted when the lift was added.",
		     actions=[{"action": "Toe boards fitted on every lift; scaffold re-tagged", "due_date": day(-19), "done": 1}]),
		dict(project=project(), occurred_on=at(-12, 14), incident_type="First aid", severity="Low", status="Closed",
		     description="A tiler cut his finger on the wet tile cutter; cleaned and dressed on site.",
		     persons_involved=[{"person_type": "Subcontractor", "supplier": TILERS, "person_name": "Jean-Bosco Ilunga", "injury": "Cut finger"}],
		     investigation="The blade guard had been taken off to cut a narrow strip.", root_cause="Guard removed for narrow cuts.",
		     actions=[{"action": "Guard refitted; narrow cuts with the jig only", "due_date": day(-11), "done": 1}]),
		dict(project=hospital(), occurred_on=at(-41, 18), incident_type="Lost time", severity="High", status="Closed",
		     description="A steel fixer stepped into the lift pit excavation at dusk and twisted his ankle.",
		     persons_involved=[{"person_type": "Employee", "employee": mavinga, "injury": "Twisted ankle", "days_lost": 3}],
		     investigation="The pit edge had tape only and no lighting after 18:00.", root_cause="No rigid edge barrier or lighting at the pit.",
		     actions=[{"action": "Rigid barrier round the pit", "due_date": day(-40), "done": 1},
		              {"action": "Floodlight on the pit after 17:30", "due_date": day(-38), "done": 1}]),
		dict(project=hospital(), occurred_on=at(-5, 11), incident_type="Property damage", severity="Medium", status="Under investigation",
		     description="The crane's jib clipped the site hoarding while slewing; two panels bent.",
		     investigation="The banksman was out of the operator's sight line during the slew.",
		     actions=[{"action": "Banksman refresher for the crane crew", "due_date": day(4), "done": 0},
		              {"action": "Replace the two hoarding panels", "due_date": day(2), "done": 1}]),
		dict(project=project(), occurred_on=at(-2, 9), incident_type="Environmental", severity="High", status="Open",
		     description="About 40 litres of diesel spilled at the site tank while refuelling the excavator; soaked into the ground.",
		     actions=[{"action": "Spill kit at the tank", "due_date": day(1), "done": 0},
		              {"action": "Bund the tank and lay a drip tray", "due_date": day(7), "done": 0}]),
	]
	made = []
	for values in plan:
		if not values["project"]:
			continue
		with as_user("requester"):
			i = frappe.get_doc({"doctype": "Site Incident", "site": site_of(values["project"]), **values})
			i.flags.ignore_permissions = True
			i.insert()
		frappe.db.set_value("Site Incident", i.name, "creation", values["occurred_on"], update_modified=False)
		made.append(i.name)
	return f"{len(made)} incidents"
