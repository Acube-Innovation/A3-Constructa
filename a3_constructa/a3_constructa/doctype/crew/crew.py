# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Crew - catalogue 7.1: a gang of site workers under a foreman.

A crew has a trade, a default site (project) and its members, each with a role and
a daily rate. The daily rate comes from the member's salary structure when there
is one (see daily_wage); the crew's daily cost is what its active members cost
for one day, and with a standard output, its labour cost per unit.

An employee belongs to one active crew at a time: saving a crew that shares an
active member with another active crew warns and names the other crew.

split_crew_hours turns a crew's hours on a day into one timesheet line per active
member; the Daily Site Report (P-06F) books crew time with it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, flt, get_datetime, getdate

DAY_START = "07:00:00"
# ERPNext costs a timesheet line only when it has an activity type; site work is execution.
DEFAULT_ACTIVITY = "Execution"
# A monthly wage is spread over the days a site works: six a week.
WORKING_DAYS = {"Daily": 1, "Weekly": 6, "Fortnightly": 12, "Bimonthly": 13, "Monthly": 26}


class Crew(Document):
	def validate(self):
		self.add_foreman()
		self.check_members()
		self.fill_daily_rates()
		self.calculate()
		self.warn_other_crews()

	def add_foreman(self):
		if self.foreman and not any(m.employee == self.foreman for m in self.members):
			self.append("members", {"employee": self.foreman, "role": "Foreman", "is_active": 1})

	def check_members(self):
		seen = set()
		for m in self.members:
			if m.employee in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(m.idx, m.employee_name or m.employee))
			seen.add(m.employee)
			name, company = frappe.db.get_value("Employee", m.employee, ["employee_name", "company"]) or (None, None)
			m.employee_name = m.employee_name or name  # a row added here (the foreman) misses the form's fetch
			if self.company and company and company != self.company:
				frappe.throw(_("Row {0}: {1} works for {2}, not {3}.").format(m.idx, m.employee_name or m.employee, company, self.company))

	def fill_daily_rates(self):
		for m in self.members:
			if not flt(m.daily_rate):
				m.daily_rate = daily_wage(m.employee, getdate())

	def calculate(self):
		active = [m for m in self.members if m.is_active]
		self.headcount = len(active)
		self.daily_cost = flt(sum(flt(m.daily_rate) for m in active), 2)
		self.unit_labour_cost = flt(self.daily_cost / flt(self.standard_output), 2) if flt(self.standard_output) else 0

	def warn_other_crews(self):
		if not self.is_active:
			return
		clashes = []
		for m in self.members:
			if not m.is_active:
				continue
			other = other_crew(m.employee, self.name)
			if other:
				clashes.append(_("{0} is already active in {1} ({2})").format(
					frappe.bold(m.employee_name or m.employee), other.crew_name, other.name))
		if clashes:
			frappe.msgprint("<br>".join(clashes) + "<br>" + _("Make them inactive in one of the crews."),
			                title=_("In another crew"), indicator="orange")


def other_crew(employee, exclude=None):
	"""The other active crew the employee is an active member of, if any."""
	rows = frappe.db.sql("""select crew.name, crew.crew_name from `tabCrew Member` m join `tabCrew` crew on crew.name = m.parent
		where m.employee = %s and m.is_active = 1 and crew.is_active = 1 and crew.name != %s limit 1""", (employee, exclude or ""), as_dict=True)
	return rows[0] if rows else None


@frappe.whitelist()
def daily_wage(employee: str, on=None) -> float:
	"""The employee's daily wage from their salary structure assignment, or 0.

	A daily payroll's base is the day's wage; a weekly, fortnightly or monthly one is
	spread over the site's working days (six a week); a structure paid by timesheet
	gives its hourly rate times the standard working day."""
	on = getdate(on)
	ssa = frappe.get_all("Salary Structure Assignment", filters={"employee": employee, "docstatus": 1, "from_date": ["<=", on]},
	                     fields=["salary_structure", "base"], order_by="from_date desc", limit=1)
	if not ssa:
		return 0
	structure = frappe.db.get_value("Salary Structure", ssa[0].salary_structure,
	                                ["payroll_frequency", "salary_slip_based_on_timesheet", "hour_rate"], as_dict=True)
	if not structure:
		return 0
	if structure.salary_slip_based_on_timesheet and flt(structure.hour_rate):
		return flt(flt(structure.hour_rate) * standard_hours(), 2)
	days = WORKING_DAYS.get(structure.payroll_frequency)
	return flt(flt(ssa[0].base) / days, 2) if days else 0


def standard_hours() -> float:
	return flt(frappe.db.get_single_value("HR Settings", "standard_working_hours")) or 8


@frappe.whitelist()
def split_crew_hours(crew: str, date, hours: float, project: str | None = None, task: str | None = None, wbs: str | None = None,
                     cost_code: str | None = None, activity_type: str | None = None) -> list[dict]:
	"""One timesheet line per active member for `hours` the crew worked on `date`.

	Each member is booked the crew's hours, from the start of the site day, on the
	project (the crew's site unless given), task, WBS and cost code; the costing
	rate is the member's daily rate over the standard working day. The activity type
	defaults to Execution, so a Timesheet keeps the rate and costs the hours."""
	c = frappe.get_doc("Crew", crew)
	c.check_permission("read")
	hours = flt(hours)
	if hours <= 0:
		frappe.throw(_("Enter the hours the crew worked."))
	if not c.is_active:
		frappe.throw(_("{0} is not an active crew.").format(c.crew_name))
	start = get_datetime(f"{getdate(date)} {DAY_START}")
	activity_type = activity_type or (DEFAULT_ACTIVITY if frappe.db.exists("Activity Type", DEFAULT_ACTIVITY) else None)
	day = standard_hours()
	lines = []
	for m in c.members:
		if not m.is_active:
			continue
		rate = flt(flt(m.daily_rate) / day, 4) if day else 0
		lines.append({
			"employee": m.employee, "employee_name": m.employee_name, "role": m.role, "crew": c.name,
			"from_time": start, "to_time": add_to_date(start, hours=hours), "hours": hours,
			"project": project or c.project, "task": task, "wbs": wbs, "cost_code": cost_code, "activity_type": activity_type,
			"costing_rate": rate, "costing_amount": flt(rate * hours, 2), "is_billable": 0,
			"description": _("{0} ({1}), {2}").format(c.crew_name, _(m.role), m.employee_name or m.employee),
		})
	if not lines:
		frappe.throw(_("{0} has no active members.").format(c.crew_name))
	return lines
