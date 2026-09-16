# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo labour: attendance on site, timesheets against WBS, and an expense claim."""

import frappe
from frappe.utils import add_days, flt, getdate

from a3_constructa.demo.common import PREFIX, company, day, log
from a3_constructa.demo.masters import EMPLOYEES, _project, employee

SITE = "Mbandaka Main Compound"

# Weekdays back from today that the demo covers.
WORKING_DAYS = 20


def run():
	create_attendance()
	create_timesheets()
	create_expense_claim()
	create_payroll_and_billing()


def create_attendance():
	"""Four weeks of attendance, tagged to the project and site.

	A couple of absences and late arrivals are included so the Site-wise
	Attendance report has an absenteeism figure worth looking at rather than a
	flat 100 per cent.
	"""
	if frappe.db.exists("Attendance", {"project": _project()}):
		log("attendance already present")
		return

	created = 0
	for offset in range(WORKING_DAYS, 0, -1):
		date = getdate(day(-offset))
		if date.weekday() >= 5:
			continue
		for index, (first, last, _designation) in enumerate(EMPLOYEES):
			emp = employee("%s %s" % (first, last))
			if not emp:
				continue
			# One absence each, on a different day per person.
			status = "Absent" if offset == 6 + index * 3 else "Present"
			doc = frappe.new_doc("Attendance")
			doc.employee = emp
			doc.attendance_date = date
			doc.status = status
			doc.company = company()
			doc.project = _project()
			doc.site = SITE
			doc.working_hours = 0 if status == "Absent" else (9 if index == 0 else 8)
			doc.late_entry = 1 if (offset % 7 == 0 and index == 1) else 0
			doc.flags.ignore_permissions = True
			doc.flags.ignore_validate = True
			doc.insert()
			doc.submit()
			created += 1
	log("attendance: %d records over %d days" % (created, WORKING_DAYS))


def create_timesheets():
	"""Staff hours booked to WBS and cost code, and to the plant they ran."""
	if frappe.db.exists("Timesheet", {"parent_project": _project()}) or frappe.db.exists(
		"Timesheet Detail", {"project": _project()}
	):
		log("timesheets already present")
		return

	activity = frappe.db.get_value("Activity Type", {}, "name")
	if not activity:
		activity = frappe.get_doc({
			"doctype": "Activity Type", "activity_type": "Site Supervision",
		}).insert(ignore_permissions=True).name

	excavator = frappe.db.get_value("Asset", {"asset_name": "Excavator 20T"}, "name")

	# Costing and billing rates are the point of a timesheet, not decoration.
	# With both left at zero every row values at nil, and ERPNext's Project
	# Profitability report returns no rows at all rather than rows of zeros -
	# so the chart on the Finance workspace draws an empty canvas.
	plan = [
		("Jean Mukendi", "MBK-W-SUB", "MBK-CC-SUB", None, 8, 14.0, 22.0),
		("Alice Kabeya", "MBK-W-SUP", "MBK-CC-BLK", None, 7, 18.0, 28.0),
		("Grace Mbuyi", "MBK-W-SUB", "MBK-CC-PLT", excavator, 9, 12.0, 19.0),
	]

	for name, wbs, code, asset, hours, costing_rate, billing_rate in plan:
		emp = employee(name)
		if not emp:
			continue
		doc = frappe.new_doc("Timesheet")
		doc.employee = emp
		doc.company = company()
		# The project on a time log costs the project; the project on the header
		# is what Project Profitability groups by. Both are needed.
		doc.parent_project = _project()
		# finance.py owns the client record; importing here rather than at module
		# level keeps the two demo stages independent of each other's order.
		from a3_constructa.demo.finance import _customer
		doc.customer = _customer()
		for offset in (12, 9, 5, 2):
			date = getdate(day(-offset))
			if date.weekday() >= 5:
				continue
			doc.append("time_logs", {
				"activity_type": activity,
				"from_time": "%s 08:00:00" % date,
				"to_time": "%s %02d:00:00" % (date, 8 + hours),
				"hours": hours,
				"is_billable": 1,
				"billing_hours": hours,
				"costing_rate": costing_rate,
				"billing_rate": billing_rate,
				"project": _project(),
				"wbs": wbs,
				"cost_code": code,
				"asset": asset,
				"description": "Site works",
			})
		if not doc.time_logs:
			continue
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
	log("timesheets: %d, booked to WBS, cost code and plant, costed and billed" % len(plan))


def create_expense_claim():
	"""A site expense claimed against the project cost code."""
	if frappe.db.exists("Expense Claim", {}):
		log("expense claim already present")
		return

	claim_type = frappe.db.get_value("Expense Claim Type", {}, "name")
	if not claim_type:
		# The HRMS install on this bench did not seed the standard claim types,
		# so the demo creates the one it needs.
		ct = frappe.new_doc("Expense Claim Type")
		ct.expense_type = "Site Expenses"
		ct.append("accounts", {
			"company": company(),
			"default_account": frappe.get_all("Account", filters={
				"company": company(), "root_type": "Expense", "is_group": 0},
				pluck="name")[0],
		})
		ct.flags.ignore_permissions = True
		ct.insert()
		claim_type = ct.name
		log("created expense claim type %s" % claim_type)

	payable = frappe.get_all("Account", filters={
		"company": company(), "account_type": "Payable", "is_group": 0}, pluck="name")
	expense = frappe.get_all("Account", filters={
		"company": company(), "root_type": "Expense", "is_group": 0}, pluck="name")
	if not (payable and expense):
		log("no payable/expense account; expense claim skipped")
		return

	doc = frappe.new_doc("Expense Claim")
	doc.employee = employee("Jean Mukendi")
	doc.company = company()
	doc.posting_date = day(-7)
	doc.payable_account = payable[0]
	doc.approval_status = "Approved"
	doc.append("expenses", {
		"expense_date": day(-8),
		"expense_type": claim_type,
		"description": "Site transport and consumables",
		"amount": 420,
		"sanctioned_amount": 420,
		"default_account": expense[0],
		"cost_center": frappe.get_all("Cost Center", filters={
			"company": company(), "is_group": 0}, pluck="name")[0],
		"project": _project(),
		"cost_head": frappe.db.get_value("Cost Head", {"cost_head_name": "University"}, "name"),
		"wbs": "MBK-W-SUB",
		"cost_code": "MBK-CC-SUB",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	doc.submit()
	log("expense claim %s: %s against MBK-CC-SUB" % (doc.name, flt(doc.total_claimed_amount)))


# --------------------------------------------------------------- payroll chain
# ERPNext's Project Profitability report earns its name from a chain, not from a
# timesheet alone: it inner-joins Timesheet to a submitted Salary Slip (what the
# hours cost) and to a submitted Sales Invoice (what they were billed for). With
# either end missing the report returns no rows at all, so the chart on the
# Finance workspace draws an empty canvas rather than a zero.
#
# These records exist to complete that chain. A construction contractor bills a
# client by progress certificate rather than by the hour, so this sits alongside
# the certificate story in finance.py rather than replacing it.
SALARY_COMPONENT = "Site Wages"
SALARY_STRUCTURE = "MBK Site Wages"
HOURLY_COST = 15.0
MONTHLY_BASE = 1200.0


def create_payroll_and_billing():
	"""Cost the timesheets through payroll and bill them to the client."""
	sheets = frappe.get_all(
		"Timesheet",
		filters={"docstatus": 1, "parent_project": _project()},
		fields=["name", "employee", "start_date", "total_hours", "total_billable_hours"],
	)
	if not sheets:
		log("no timesheets to cost or bill")
		return

	_holiday_list()
	_salary_structure()
	_assign_structure(sheets)
	_salary_slips(sheets)
	_invoice_timesheets(sheets)


def _holiday_list() -> str | None:
	"""A company holiday list, without which no salary slip can be produced.

	A salary slip works out payment days by subtracting holidays, so it refuses
	to save until the employee or the company has a list. The setup wizard does
	not create one, so any site doing payroll needs this - it is not particular
	to the demo. Sundays only; public holidays are the client's to add.
	"""
	default = frappe.db.get_value("Company", company(), "default_holiday_list")
	if default:
		return default

	fiscal = frappe.db.get_value(
		"Fiscal Year", {"disabled": 0}, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not fiscal:
		log("no fiscal year; holiday list skipped")
		return None

	name = "%s Site Calendar" % PREFIX
	if not frappe.db.exists("Holiday List", name):
		doc = frappe.new_doc("Holiday List")
		doc.holiday_list_name = name
		doc.from_date = fiscal.year_start_date
		doc.to_date = fiscal.year_end_date
		doc.weekly_off = "Sunday"
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.get_weekly_off_dates()
		doc.save()
		log("holiday list %s: %d Sundays" % (doc.name, len(doc.holidays)))

	frappe.db.set_value("Company", company(), "default_holiday_list", name)
	return name


def _salary_structure() -> str:
	"""A timesheet-based structure: gross pay follows the hours booked."""
	if not frappe.db.exists("Salary Component", SALARY_COMPONENT):
		frappe.get_doc({
			"doctype": "Salary Component",
			"salary_component": SALARY_COMPONENT,
			"salary_component_abbr": "SW",
			"type": "Earning",
			"depends_on_payment_days": 0,
			"accounts": [{"company": company()}],
		}).insert(ignore_permissions=True)

	if frappe.db.exists("Salary Structure", SALARY_STRUCTURE):
		return SALARY_STRUCTURE

	doc = frappe.new_doc("Salary Structure")
	doc.name = SALARY_STRUCTURE
	doc.company = company()
	doc.payroll_frequency = "Monthly"
	# This is the switch that makes gross pay = hours x hour_rate.
	doc.salary_slip_based_on_timesheet = 1
	doc.salary_component = SALARY_COMPONENT
	doc.hour_rate = HOURLY_COST
	doc.payment_account = frappe.db.get_value(
		"Account", {"company": company(), "account_type": "Bank", "is_group": 0}, "name"
	)
	doc.append("earnings", {"salary_component": SALARY_COMPONENT, "amount": 0})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("salary structure %s at %s/hour" % (doc.name, HOURLY_COST))
	return doc.name


def _assign_structure(sheets):
	"""One assignment per employee, effective before the earliest timesheet."""
	from frappe.utils import get_first_day

	start = get_first_day(min(s.start_date for s in sheets))
	made = 0
	for emp in {s.employee for s in sheets}:
		if frappe.db.exists("Salary Structure Assignment",
		                    {"employee": emp, "salary_structure": SALARY_STRUCTURE,
		                     "docstatus": 1}):
			continue
		doc = frappe.new_doc("Salary Structure Assignment")
		doc.employee = emp
		doc.salary_structure = SALARY_STRUCTURE
		doc.company = company()
		doc.from_date = start
		doc.base = MONTHLY_BASE
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		made += 1
	if made:
		log("salary structure assignments: %d from %s" % (made, start))


def _salary_slips(sheets):
	"""A submitted slip per timesheet - the cost side of profitability."""
	from frappe.utils import get_first_day, get_last_day

	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

	made = 0
	for sheet in sheets:
		if frappe.db.exists("Salary Slip Timesheet", {"time_sheet": sheet.name, "docstatus": 1}):
			continue
		slip = make_salary_slip(SALARY_STRUCTURE, employee=sheet.employee,
		                        ignore_permissions=True)
		slip.company = company()
		slip.payroll_frequency = "Monthly"
		slip.start_date = get_first_day(sheet.start_date)
		slip.end_date = get_last_day(sheet.start_date)
		slip.posting_date = get_last_day(sheet.start_date)
		slip.set("timesheets", [])
		slip.append("timesheets", {
			"time_sheet": sheet.name,
			"working_hours": sheet.total_hours,
		})
		slip.flags.ignore_permissions = True
		slip.insert()
		slip.submit()
		made += 1
	if made:
		log("salary slips: %d, costed from the timesheets" % made)


def _invoice_timesheets(sheets):
	"""A submitted invoice per timesheet - the revenue side of profitability."""
	from erpnext.projects.doctype.timesheet.timesheet import make_sales_invoice

	from a3_constructa.demo.finance import _customer

	item = frappe.db.get_value("Item", {"item_code": "MBK-SVC-INSTALL"}, "name") or \
		frappe.db.get_value("Item", {"is_stock_item": 0}, "name")
	if not item:
		log("no service item to bill hours against")
		return

	made = 0
	for sheet in sheets:
		if not sheet.total_billable_hours:
			continue
		if frappe.db.exists("Sales Invoice Timesheet", {"time_sheet": sheet.name, "docstatus": 1}):
			continue
		invoice = make_sales_invoice(sheet.name, item_code=item, customer=_customer())
		invoice.posting_date = getdate(day(-1))
		invoice.due_date = getdate(day(29))
		invoice.project = _project()
		invoice.flags.ignore_permissions = True
		invoice.flags.ignore_mandatory = True
		invoice.insert()
		invoice.submit()
		made += 1
	if made:
		log("timesheet sales invoices: %d, billed to the client" % made)
