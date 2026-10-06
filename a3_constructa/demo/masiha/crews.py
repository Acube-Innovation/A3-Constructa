# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-07A: site crews on the Administrative Centre and the hospital.

The site workers (invented) are on two salary structures: tradesmen and helpers on
a daily wage, foremen on a monthly salary (spread over 26 site days). One steel
fixer's helper has no salary structure yet, so his crew rate was typed in.

- Tiling gang A: foreman, two tilers, a helper; a second helper moved to the
  labour pool and is inactive here. 24 m² a day.
- Blockwork gang: foreman, two masons, two helpers. 22 m² a day.
- Steel fixers (hospital): foreman, two fixers, a helper. 1.2 t a day.
- Formwork gang: disbanded when the frame was struck.
- General labour pool: no foreman; includes the tiling helper who is still active
  in Tiling gang A as well, so saving it warns.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, log, project

DAILY, MONTHLY = "MSS Site Daily Wage", "MSS Site Monthly Staff"
# first, last, gender, designation, structure, base
WORKERS = {
	"mukendi": ("Jean-Pierre", "Mukendi", "Male", "Foreman", MONTHLY, 990),
	"bokele": ("Alain", "Bokele", "Male", "Tiler", DAILY, 28),
	"ngoy": ("Fiston", "Ngoy", "Male", "Tiler", DAILY, 28),
	"kabeya": ("Dieudonné", "Kabeya", "Male", "Site Helper", DAILY, 14),
	"lufungula": ("Serge", "Lufungula", "Male", "Site Helper", DAILY, 14),
	"tshilombo": ("Papy", "Tshilombo", "Male", "Foreman", MONTHLY, 960),
	"kalonji": ("Junior", "Kalonji", "Male", "Mason", DAILY, 26),
	"mbuyi": ("Gloire", "Mbuyi", "Female", "Mason", DAILY, 26),
	"bope": ("Christian", "Bope", "Male", "Site Helper", DAILY, 14),
	"lumbala": ("Héritier", "Lumbala", "Male", "Site Helper", DAILY, 14),
	"kanku": ("Moïse", "Kanku", "Male", "Foreman", MONTHLY, 1020),
	"mavinga": ("Trésor", "Mavinga", "Male", "Steel Fixer", DAILY, 27),
	"kitenge": ("Blaise", "Kitenge", "Male", "Steel Fixer", DAILY, 27),
	"nzinga": ("Glody", "Nzinga", "Male", "Site Helper", None, None),
	"mpiana": ("Arsène", "Mpiana", "Male", "Carpenter", DAILY, 25),
	"omari": ("Rachidi", "Omari", "Male", "Site Helper", DAILY, 12),
	"kayembe": ("Nadine", "Kayembe", "Female", "Site Helper", DAILY, 12),
}
# name, trade, project key, foreman, standard output, uom, active, [(worker, role, active, typed rate)]
CREWS = [
	("Tiling gang A", "Tiling", "admin", "mukendi", 24, "Square Meter", 1,
	 [("bokele", "Tradesman", 1, None), ("ngoy", "Tradesman", 1, None), ("kabeya", "Helper", 1, None), ("lufungula", "Helper", 0, None)]),
	("Blockwork gang", "Masonry", "admin", "tshilombo", 22, "Square Meter", 1,
	 [("kalonji", "Tradesman", 1, None), ("mbuyi", "Tradesman", 1, None), ("bope", "Helper", 1, None), ("lumbala", "Helper", 1, None)]),
	("Steel fixers", "Steel fixing", "hospital", "kanku", 1.2, "Tonne", 1,
	 [("mavinga", "Tradesman", 1, None), ("kitenge", "Tradesman", 1, None), ("nzinga", "Helper", 1, 15)]),
	("Formwork gang", "Formwork", "admin", None, 30, "Square Meter", 0,
	 [("mpiana", "Tradesman", 0, None)]),
	("General labour pool", "General labour", "admin", None, None, None, 1,
	 [("omari", "Helper", 1, None), ("kayembe", "Helper", 1, None), ("lufungula", "Helper", 1, None), ("kabeya", "Helper", 1, None)]),
]


def run():
	if frappe.db.exists("Crew", {"crew_name": CREWS[0][0]}):
		log("crews already present")
		return
	employees = workers()
	structures()
	assign(employees)
	made = [crew(employees, *c) for c in CREWS]
	log("Crews: " + "; ".join(made))


def workers():
	out = {}
	for key, (first, last, gender, designation, _structure, _base) in WORKERS.items():
		if not frappe.db.exists("Designation", designation):
			frappe.get_doc({"doctype": "Designation", "designation_name": designation}).insert(ignore_permissions=True)
		name = frappe.db.get_value("Employee", {"first_name": first, "last_name": last, "company": COMPANY}, "name")
		if not name:
			e = frappe.get_doc({"doctype": "Employee", "first_name": first, "last_name": last, "gender": gender, "company": COMPANY,
			                    "date_of_birth": "1990-03-01", "date_of_joining": day(-200), "status": "Active", "designation": designation,
			                    "department": f"Operations - {frappe.get_cached_value('Company', COMPANY, 'abbr')}"})
			e.flags.ignore_permissions = True
			e.insert()
			name = e.name
		out[key] = name
	return out


def structures():
	for name, frequency in ((DAILY, "Daily"), (MONTHLY, "Monthly")):
		if frappe.db.exists("Salary Structure", name):
			continue
		s = frappe.get_doc({"doctype": "Salary Structure", "name": name, "__newname": name, "company": COMPANY, "currency": "USD",
		                    "payroll_frequency": frequency, "is_active": "Yes",
		                    "earnings": [{"salary_component": "Basic", "amount_based_on_formula": 1, "formula": "base"}]})
		s.flags.ignore_permissions = True
		s.insert()
		s.submit()


def assign(employees):
	for key, (_f, _l, _g, _d, structure, base) in WORKERS.items():
		if not structure or frappe.db.exists("Salary Structure Assignment", {"employee": employees[key], "docstatus": 1}):
			continue
		a = frappe.get_doc({"doctype": "Salary Structure Assignment", "employee": employees[key], "salary_structure": structure,
		                    "company": COMPANY, "currency": "USD", "from_date": day(-200), "base": base})
		a.flags.ignore_permissions = True
		a.insert()
		a.submit()


def crew(employees, name, trade, site, foreman, output, uom, active, members):
	sites = {"admin": project(), "hospital": frappe.db.get_value("Project", {"project_name": ["like", "Hospital extension%"]}, "name")}
	with as_user("pm"):
		c = frappe.get_doc({"doctype": "Crew", "crew_name": name, "trade": trade, "company": COMPANY, "project": sites[site],
		                    "foreman": employees.get(foreman), "standard_output": output, "output_uom": uom, "is_active": 1,
		                    "members": [{"employee": employees[w], "role": r, "is_active": a, "daily_rate": rate} for w, r, a, rate in members]})
		c.flags.ignore_permissions = True
		c.insert()
		if not active:
			c.is_active = 0
			c.save()
	frappe.db.set_value("Crew", c.name, {"creation": at(-150 if name != "General labour pool" else -20, 9)}, update_modified=False)
	if not active:
		comment("Crew", c.name, "Frame struck; the formwork carpenters went back to the joinery shop. Crew disbanded.", "pm", at(-25, 16))
	return f"{c.name} {name} ({c.headcount} active, ${c.daily_cost:,.2f}/day)"
