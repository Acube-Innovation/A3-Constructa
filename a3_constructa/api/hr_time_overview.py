# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "HR & Time Overview" tab of the HR & Time workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency, from the
documents' base amounts. Employee Checkin carries no company, so it is narrowed
through its employee.

People data is handed back as counts and totals only. Names appear in the
approvals list, never next to what anyone is paid.

Attended means an attendance of Present, Work From Home or Half Day, as the
Project-wise Manpower Cost report counts a man-day. On leave today is read from
approved Leave Applications, since attendance for leave is often marked after
the day. Payroll cost is the gross pay of submitted salary slips, and a payroll
run is the slips sharing the latest pay period end date.

The filters handed back beside each figure name the company too, so the list a
row opens on shows exactly the records counted.
"""

from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, flt, get_first_day, get_last_day, getdate, now_datetime, today

from a3_constructa.a3_constructa.report.site_wise_attendance.site_wise_attendance import PRESENT_STATUSES
from a3_constructa.api.utils import company_projects, default_company, default_currency

DOCTYPES = (
	"Employee",
	"Attendance",
	"Employee Checkin",
	"Leave Application",
	"Salary Slip",
	"Salary Structure Assignment",
	"Expense Claim",
	"Employee Advance",
	"Timesheet",
)

ATTENDED = (*PRESENT_STATUSES, "Half Day")
ATTENDANCE_STATUSES = ("Present", "Work From Home", "Half Day", "On Leave", "Absent")

# A claim counts as money claimed unless it was turned down or cancelled.
CLAIMED = {"docstatus": ["<", 2], "approval_status": ["!=", "Rejected"]}
LEAVE_WAITING = {"docstatus": 0, "status": "Open"}
CLAIM_WAITING = {"docstatus": 0, "approval_status": "Draft"}
# Paid out and not yet claimed or returned in full, or approved and not yet paid.
ADVANCE_OPEN = {"docstatus": 1, "status": ["in", ["Unpaid", "Paid"]]}

CLAIM_WAIT_DAYS = 14
AWAITING_ROWS = 8
TOP_GROUPS = 5
TREND_MONTHS = 12


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {dt for dt in DOCTYPES if frappe.has_permission(dt, "read")}
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"month_start": str(get_first_day(now)),
		"workforce": _workforce(readable, now),
		"today": _today(readable, now),
		"attendance": _attendance(readable, now),
		"leave": _leave(readable, now),
		"payroll": _payroll(readable, now),
		"expenses": _expenses(readable, now),
		"timesheets": _timesheets(readable, now),
		"awaiting": _awaiting(readable, now),
		"health": _health(readable, now),
	}


def _scoped(doctype, filters=None):
	"""`filters` narrowed to the default company, as a list of conditions."""
	if isinstance(filters, dict):
		conditions = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
	else:
		conditions = list(filters or [])
	company = default_company()
	if company and not any(c[0] == doctype and c[1] == "company" for c in conditions):
		meta = frappe.get_meta(doctype)
		if meta.has_field("company"):
			conditions.append([doctype, "company", "=", company])
		elif meta.has_field("project"):
			conditions.append([doctype, "project", "in", company_projects(company) or [""]])
		elif meta.has_field("employee"):
			conditions.append([doctype, "employee", "in", _company_employees(company) or [""]])
	return conditions


def _listed(doctype, filters) -> dict:
	"""`filters` with the company named, for the list a figure opens on."""
	company = default_company()
	if company and frappe.get_meta(doctype).has_field("company"):
		return {**filters, "company": company}
	return dict(filters)


def _company_employees(company) -> list[str]:
	"""The company's employees, for doctypes that carry an employee but no company."""
	return frappe.get_all("Employee", filters={"company": company}, pluck="name")


def _count(doctype, filters=None) -> int:
	return frappe.get_list(doctype, filters=_scoped(doctype, filters), fields=["count(name) as n"])[0].n


def _statuses(doctype, order, filters=None) -> list[dict]:
	found = {
		row.status: row.n
		for row in frappe.get_list(
			doctype, filters=_scoped(doctype, filters), fields=["status", "count(name) as n"], group_by="status"
		)
	}
	return [{"label": _(status), "value": status, "count": found[status]} for status in order if found.get(status)]


def _top(rows, limit, measure="count") -> list[dict]:
	"""The largest `limit` groups, the rest folded into one "Other" row."""
	rows = sorted(rows, key=lambda row: -flt(row[measure]))
	top = rows[:limit]
	rest = rows[limit:]
	if rest:
		top.append(
			{
				"label": _("Other"),
				"value": None,
				"count": sum(row["count"] for row in rest),
				"amount": sum(flt(row.get("amount")) for row in rest),
				"other": True,
			}
		)
	return top


def _titles(doctype, names, field) -> dict:
	"""Display titles for link values, where the caller may read them."""
	names = [name for name in names if name]
	if not names or not frappe.has_permission(doctype, "read"):
		return {}
	return {
		row.name: row[field]
		for row in frappe.get_list(doctype, filters={"name": ["in", names]}, fields=["name", field], limit_page_length=0)
	}


def _grouped(found, titles=None) -> list[dict]:
	"""Rows for a breakdown from {value: count} or {value: (count, amount)}."""
	rows = []
	for value, figures in found.items():
		count, amount = figures if isinstance(figures, tuple) else (figures, None)
		row = {"label": (titles or {}).get(value) or value or _("Not set"), "value": value or None, "count": count}
		if amount is not None:
			row["amount"] = amount
		rows.append(row)
	return rows


# ---------------------------------------------------------------- sections


def _workforce(readable, now) -> dict:
	if "Employee" not in readable:
		return {"restricted": True}

	active = _listed("Employee", {"status": "Active"})
	people = frappe.get_list(
		"Employee",
		filters=_scoped("Employee", active),
		fields=["department", "designation"],
		limit_page_length=0,
	)
	departments = Counter(row.department for row in people)
	designations = Counter(row.designation for row in people)
	year = ["between", [str(add_months(now, -12)), str(now)]]

	return {
		"restricted": False,
		"filters": active,
		"active": len(people),
		"joined": _count("Employee", {"date_of_joining": year}),
		"left": _count("Employee", {"relieving_date": year}),
		"by_department": _top(
			_grouped(departments, _titles("Department", list(departments), "department_name")), TOP_GROUPS
		),
		"by_designation": _top(_grouped(designations), TOP_GROUPS),
	}


def _today(readable, now) -> dict:
	"""Who is in, out and away today."""
	day = str(now)

	def cell(doctype, filters):
		if doctype not in readable:
			return {"restricted": True, "doctype": doctype}
		filters = _listed(doctype, filters)
		return {"restricted": False, "doctype": doctype, "filters": filters, "count": _count(doctype, filters)}

	marked = {"docstatus": 1, "attendance_date": day}
	checked_in = {"restricted": True, "doctype": "Employee Checkin"}
	if "Employee Checkin" in readable:
		# People, not punches: one person checks in and out several times a day.
		checked_in = {
			"restricted": False,
			"doctype": "Employee Checkin",
			"count": frappe.get_list(
				"Employee Checkin",
				filters=_scoped("Employee Checkin", {"time": ["between", [day, day]]}),
				fields=["count(distinct employee) as n"],
			)[0].n,
		}

	return {
		"date": day,
		"present": cell("Attendance", {**marked, "status": ["in", list(ATTENDED)]}),
		"absent": cell("Attendance", {**marked, "status": "Absent"}),
		"on_leave": cell(
			"Leave Application",
			{"docstatus": 1, "status": "Approved", "from_date": ["<=", day], "to_date": [">=", day]},
		),
		"checked_in": checked_in,
	}


def _attendance(readable, now) -> dict:
	if "Attendance" not in readable:
		return {"restricted": True}

	month = _listed("Attendance", {"docstatus": 1, "attendance_date": [">=", str(get_first_day(now))]})
	attended = {**month, "status": ["in", list(ATTENDED)]}
	projects = {
		row.project: row.n
		for row in frappe.get_list(
			"Attendance",
			filters=_scoped("Attendance", attended),
			fields=["project", "count(name) as n"],
			group_by="project",
		)
	}
	return {
		"restricted": False,
		"filters": month,
		"attended_filters": attended,
		"by_status": _statuses("Attendance", ATTENDANCE_STATUSES, month),
		"by_project": _top(_grouped(projects, _titles("Project", list(projects), "project_name")), TOP_GROUPS),
	}


def _leave(readable, now) -> dict:
	if "Leave Application" not in readable:
		return {"restricted": True}

	# Approved leave falling at least partly inside this month.
	month = _listed(
		"Leave Application",
		{
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", str(get_last_day(now))],
			"to_date": [">=", str(get_first_day(now))],
		},
	)
	types = {
		row.leave_type: row.n
		for row in frappe.get_list(
			"Leave Application",
			filters=_scoped("Leave Application", month),
			fields=["leave_type", "count(name) as n"],
			group_by="leave_type",
		)
	}
	return {"restricted": False, "filters": month, "by_type": _top(_grouped(types), TOP_GROUPS)}


def _payroll(readable, now) -> dict:
	if "Salary Slip" not in readable:
		return {"restricted": True}

	submitted = {"docstatus": 1}
	last_end = frappe.get_list(
		"Salary Slip", filters=_scoped("Salary Slip", submitted), fields=["max(end_date) as d"]
	)[0].d
	last_run = None
	if last_end:
		row = frappe.get_list(
			"Salary Slip",
			filters=_scoped("Salary Slip", {**submitted, "end_date": str(last_end)}),
			fields=["min(start_date) as start", "sum(base_gross_pay) as amount", "count(name) as n"],
		)[0]
		last_run = {"start": row.start, "end": last_end, "amount": flt(row.amount), "count": row.n}

	first = get_first_day(add_months(now, -(TREND_MONTHS - 1)))
	months = {}
	for row in frappe.get_list(
		"Salary Slip",
		filters=_scoped("Salary Slip", {**submitted, "end_date": [">=", str(first)]}),
		fields=["end_date", "sum(base_gross_pay) as amount", "count(name) as n"],
		group_by="end_date",
	):
		key = str(row.end_date)[:7]
		amount, count = months.get(key, (0, 0))
		months[key] = (amount + flt(row.amount), count + row.n)

	trend = []
	for step in range(TREND_MONTHS):
		key = str(add_months(first, step))[:7]
		amount, count = months.get(key, (0, 0))
		trend.append({"month": key, "amount": amount, "count": count})

	return {"restricted": False, "last_run": last_run, "trend": trend}


def _expenses(readable, now) -> dict:
	if "Expense Claim" not in readable:
		return {"restricted": True}

	recent = {**CLAIMED, "posting_date": [">=", str(add_days(now, -30))]}
	row = frappe.get_list(
		"Expense Claim",
		filters=_scoped("Expense Claim", recent),
		fields=["sum(total_claimed_amount) as amount", "count(name) as n"],
	)[0]

	year = _listed("Expense Claim", {**CLAIMED, "posting_date": [">=", str(add_months(now, -12))]})
	projects = {
		row.project: (row.n, flt(row.amount))
		for row in frappe.get_list(
			"Expense Claim",
			filters=_scoped("Expense Claim", year),
			fields=["project", "sum(total_claimed_amount) as amount", "count(name) as n"],
			group_by="project",
		)
	}
	# A claim with lines of several types counts once under each of them.
	types = {
		row.expense_type: (row.n, flt(row.amount))
		for row in frappe.get_list(
			"Expense Claim",
			filters=_scoped("Expense Claim", year),
			fields=[
				"`tabExpense Claim Detail`.expense_type as expense_type",
				"sum(`tabExpense Claim Detail`.amount) as amount",
				"count(distinct `tabExpense Claim`.name) as n",
			],
			group_by="`tabExpense Claim Detail`.expense_type",
		)
	}
	by_project = _grouped(projects, _titles("Project", list(projects), "project_name"))
	by_type = _grouped(types)

	return {
		"restricted": False,
		"amount_30d": flt(row.amount),
		"count_30d": row.n,
		"waiting_30d": _count("Expense Claim", {**recent, **CLAIM_WAITING}),
		"year_filters": year,
		"by_project": _top(by_project, TOP_GROUPS, measure="amount"),
		"project_total": sum(r["amount"] for r in by_project),
		"by_type": _top(by_type, TOP_GROUPS, measure="amount"),
		"type_total": sum(r["amount"] for r in by_type),
	}


def _timesheets(readable, now) -> dict:
	if "Timesheet" not in readable:
		return {"restricted": True}

	month = _listed("Timesheet", {"docstatus": ["<", 2], "start_date": [">=", str(get_first_day(now))]})
	row = frappe.get_list(
		"Timesheet",
		filters=_scoped("Timesheet", month),
		fields=["sum(total_hours) as hours", "count(name) as n"],
	)[0]
	# The project sits on each time log, so a timesheet spanning two projects
	# counts under both; its list opens on the same child-table filter.
	projects = {
		row.project: (row.n, flt(row.amount))
		for row in frappe.get_list(
			"Timesheet",
			filters=_scoped("Timesheet", month),
			fields=[
				"`tabTimesheet Detail`.project as project",
				"sum(`tabTimesheet Detail`.base_costing_amount) as amount",
				"count(distinct `tabTimesheet`.name) as n",
			],
			group_by="`tabTimesheet Detail`.project",
		)
	}
	return {
		"restricted": False,
		"filters": month,
		"hours": flt(row.hours, 1),
		"count": row.n,
		"projects": sum(1 for project in projects if project),
		"by_project": _top(_grouped(projects, _titles("Project", list(projects), "project_name")), TOP_GROUPS),
	}


def _awaiting(readable, now) -> dict:
	"""Leave applications and expense claims waiting for a decision, oldest first."""
	leave = "Leave Application" in readable
	claims = "Expense Claim" in readable
	if not leave and not claims:
		return {"restricted": True}

	rows = []
	if leave:
		for row in frappe.get_list(
			"Leave Application",
			filters=_scoped("Leave Application", LEAVE_WAITING),
			fields=["name", "employee_name", "leave_type", "from_date", "total_leave_days"],
			order_by="from_date asc",
			limit_page_length=AWAITING_ROWS,
		):
			rows.append(
				{
					"doctype": "Leave Application",
					"name": row.name,
					"employee_name": row.employee_name,
					"leave_type": row.leave_type,
					"days": flt(row.total_leave_days, 1),
					"date": row.from_date,
					# The leave has begun and nobody has decided on it.
					"late": bool(row.from_date and getdate(row.from_date) <= now),
				}
			)
	if claims:
		found = frappe.get_list(
			"Expense Claim",
			filters=_scoped("Expense Claim", CLAIM_WAITING),
			fields=["name", "employee_name", "project", "posting_date"],
			order_by="posting_date asc",
			limit_page_length=AWAITING_ROWS,
		)
		titles = _titles("Project", list({row.project for row in found}), "project_name")
		for row in found:
			rows.append(
				{
					"doctype": "Expense Claim",
					"name": row.name,
					"employee_name": row.employee_name,
					"project": titles.get(row.project) or row.project,
					"date": row.posting_date,
					"late": bool(row.posting_date and date_diff(now, row.posting_date) > CLAIM_WAIT_DAYS),
				}
			)

	rows.sort(key=lambda row: (row["date"] is None, str(row["date"] or ""), row["name"]))
	total = (_count("Leave Application", LEAVE_WAITING) if leave else 0) + (
		_count("Expense Claim", CLAIM_WAITING) if claims else 0
	)
	return {"restricted": False, "rows": rows[:AWAITING_ROWS], "total": total}


def _health(readable, now) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for people payroll would leave out.
	"""
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append(
			{"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta}
		)

	def counted(doctype, filters):
		return _count(doctype, filters) if doctype in readable else None

	unassigned = None
	if {"Employee", "Salary Structure Assignment"} <= readable:
		assigned = set(
			frappe.get_list(
				"Salary Structure Assignment",
				filters=_scoped("Salary Structure Assignment", {"docstatus": 1}),
				pluck="employee",
				limit_page_length=0,
			)
		)
		unassigned = sorted(
			name
			for name in frappe.get_list(
				"Employee", filters=_scoped("Employee", {"status": "Active"}), pluck="name", limit_page_length=0
			)
			if name not in assigned
		)
	# Without access, the row names whichever of the two the caller cannot read.
	missing = [dt for dt in ("Employee", "Salary Structure Assignment") if dt not in readable]
	check(
		"Active employees with no salary structure",
		"critical",
		missing[0] if missing else "Employee",
		len(unassigned) if unassigned is not None else None,
		{"name": ["in", unassigned or []]},
		meta=_("Payroll leaves them out"),
	)

	leave = _listed("Leave Application", LEAVE_WAITING)
	begun = None
	if "Leave Application" in readable:
		begun = _count("Leave Application", {**leave, "from_date": ["<=", str(now)]})
	check(
		"Leave applications awaiting approval",
		"warning",
		"Leave Application",
		counted("Leave Application", leave),
		leave,
		meta=_("{0} already begun").format(begun) if begun else None,
	)

	claims = _listed("Expense Claim", CLAIM_WAITING)
	check("Expense claims awaiting approval", "warning", "Expense Claim", counted("Expense Claim", claims), claims)

	advances = _listed("Employee Advance", ADVANCE_OPEN)
	check(
		"Employee advances not yet settled",
		"warning",
		"Employee Advance",
		counted("Employee Advance", advances),
		advances,
		meta=_("Unpaid, or paid and not yet claimed or returned"),
	)

	slips = _listed("Salary Slip", {"docstatus": 0})
	check("Salary slips still in draft", "warning", "Salary Slip", counted("Salary Slip", slips), slips)

	timesheets = _listed("Timesheet", {"docstatus": 0})
	check("Timesheets not yet submitted", "warning", "Timesheet", counted("Timesheet", timesheets), timesheets)

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
