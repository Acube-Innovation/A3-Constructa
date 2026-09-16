# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Project-wise Manpower Cost - build sheet head 64, row 41.

What labour cost each project carried, and what a man-day cost there.

Two sources, because neither covers everyone. Staff who fill timesheets have
their hours costed against a project, WBS and cost code already, and that is
used as-is. Site labour does not fill timesheets, so their salary slip is spread
across the projects they were marked present on, pro rata by man-days. The
`basis` column says which applied to each row, so a number is never silently a
mixture of a measurement and an estimate.

Overtime is taken from Additional Salary rather than inferred from hours, since
that is where an overtime payout is actually recorded.
"""

import frappe
from frappe import _
from frappe.utils import flt

GROUP_FIELDS = {
	"Project": "project",
	"Cost Head": "cost_head",
	"WBS": "wbs",
	"Cost Code": "cost_code",
}
LINK_OPTIONS = {"project": "Project", "cost_head": "Cost Head",
                "wbs": "WBS", "cost_code": "Cost Code"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by = filters.get("group_by") or "Project"
	field = GROUP_FIELDS.get(group_by, "project")

	buckets = {}

	# --- measured: hours costed on timesheets -----------------------------
	for r in get_timesheet_cost(filters):
		key = r.get(field) or _("Not Set")
		b = bucket(buckets, key)
		b["regular_cost"] += flt(r.costing_amount)
		b["man_days"] += flt(r.hours) / 8.0
		b["employees"].add(r.employee)
		b["_timesheet"] = True

	# --- apportioned: payroll spread over attended projects ---------------
	attendance = get_attendance_days(filters)
	for employee, days_by_key in attendance.items():
		total_days = sum(days_by_key.values())
		if not total_days:
			continue

		# Man-days are recorded whether or not payroll has been run. A project
		# part-way through the month has attendance and no salary slips yet, and
		# it should still show its headcount rather than disappear.
		pay = get_employee_pay(employee, filters)

		for key, days in days_by_key.items():
			share = days / total_days
			b = bucket(buckets, key)
			b["man_days"] += days
			b["employees"].add(employee)
			if pay:
				b["regular_cost"] += flt(pay["regular"]) * share
				b["ot_cost"] += flt(pay["overtime"]) * share
				b["_apportioned"] = True
			else:
				b["_no_payroll"] = True

	data = []
	for b in buckets.values():
		b["headcount"] = len(b.pop("employees"))
		b["total_cost"] = b["regular_cost"] + b["ot_cost"]
		b["cost_per_man_day"] = (b["total_cost"] / b["man_days"]) if b["man_days"] else 0
		b["basis"] = basis_label(b.pop("_timesheet", False), b.pop("_apportioned", False),
		                         b.pop("_no_payroll", False))
		data.append(b)

	data.sort(key=lambda r: r["total_cost"], reverse=True)
	return get_columns(group_by, field), data


def bucket(buckets, key):
	return buckets.setdefault(key, {
		"grouping": key, "headcount": 0, "man_days": 0.0,
		"regular_cost": 0.0, "ot_cost": 0.0, "employees": set(),
	})


def basis_label(timesheet, apportioned, no_payroll):
	"""Say how each row was arrived at, so a figure is never silently mixed."""
	parts = []
	if timesheet:
		parts.append(_("Timesheet"))
	if apportioned:
		parts.append(_("Apportioned"))
	if no_payroll:
		# Man-days counted, but payroll for the period has not been run.
		parts.append(_("Man-days only"))
	return " + ".join(parts) if parts else ""


def get_columns(label, field):
	return [
		{"fieldname": "grouping", "label": _(label), "fieldtype": "Link",
		 "options": LINK_OPTIONS.get(field), "width": 180},
		{"fieldname": "headcount", "label": _("Headcount"), "fieldtype": "Int", "width": 100},
		{"fieldname": "man_days", "label": _("Man-days"), "fieldtype": "Float",
		 "precision": 1, "width": 110},
		{"fieldname": "regular_cost", "label": _("Regular Cost"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "ot_cost", "label": _("OT Cost"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_cost", "label": _("Total Cost"), "fieldtype": "Currency",
		 "width": 150},
		{"fieldname": "cost_per_man_day", "label": _("Cost / Man-day"),
		 "fieldtype": "Currency", "width": 140},
		{"fieldname": "basis", "label": _("Basis"), "fieldtype": "Data", "width": 170},
	]


def get_timesheet_cost(filters):
	conditions = ["ts.docstatus = 1", "td.project is not null", "td.project != ''"]
	values = {}
	if filters.get("project"):
		conditions.append("td.project = %(project)s")
		values["project"] = filters.project
	if filters.get("from_date"):
		conditions.append("ts.start_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("ts.end_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		"""
		select ts.employee, td.project, td.wbs, td.cost_code, td.hours,
		       td.base_costing_amount as costing_amount,
		       wbs.cost_head as cost_head
		from `tabTimesheet Detail` td
		inner join `tabTimesheet` ts on ts.name = td.parent
		left join `tabWBS` wbs on wbs.name = td.wbs
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def get_attendance_days(filters):
	"""Present days per employee, keyed by every grouping the report offers."""
	conditions = ["a.docstatus = 1", "a.status in ('Present', 'Half Day', 'Work From Home')"]
	values = {}
	if filters.get("project"):
		conditions.append("a.project = %(project)s")
		values["project"] = filters.project
	if filters.get("from_date"):
		conditions.append("a.attendance_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("a.attendance_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select a.employee, a.project, a.status, count(*) as days
		from `tabAttendance` a
		where {conditions}
		group by a.employee, a.project, a.status
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	out = {}
	for r in rows:
		key = r.project or _("Not Set")
		# A half day is half a man-day.
		days = flt(r.days) * (0.5 if r.status == "Half Day" else 1.0)
		out.setdefault(r.employee, {})
		out[r.employee][key] = out[r.employee].get(key, 0) + days
	return out


def get_employee_pay(employee, filters):
	"""Payroll cost for the employee in the period, split regular vs overtime."""
	conditions = ["ss.docstatus = 1", "ss.employee = %(employee)s"]
	values = {"employee": employee}
	if filters.get("from_date"):
		conditions.append("ss.start_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("ss.end_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	slips = frappe.db.sql(
		"""
		select sum(ss.gross_pay) as gross
		from `tabSalary Slip` ss
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	gross = flt(slips[0].gross) if slips else 0
	if not gross:
		return None

	overtime = get_overtime(employee, filters)
	# Overtime is part of gross pay, so regular is what is left of it.
	return {"regular": max(gross - overtime, 0), "overtime": overtime}


def get_overtime(employee, filters):
	"""Overtime paid to the employee in the period.

	Read from Additional Salary, which is where head 59 row 13 routes an overtime
	payout, rather than inferred from hours worked. Components are matched by
	name because what a client calls overtime varies.
	"""
	conditions = {"docstatus": 1, "employee": employee,
	              "salary_component": ["like", "%Overtime%"]}
	if filters.get("from_date"):
		conditions["payroll_date"] = [">=", filters.from_date]
	if filters.get("to_date"):
		conditions["payroll_date"] = ["<=", filters.to_date]

	rows = frappe.get_all("Additional Salary", filters=conditions, pluck="amount")
	return sum(flt(a) for a in rows)
