# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo labour: attendance on site, timesheets against WBS, and an expense claim."""

import frappe
from frappe.utils import add_days, flt, getdate

from a3_constructa.demo.common import company, day, log
from a3_constructa.demo.masters import EMPLOYEES, _project, employee

SITE = "Mbandaka Main Compound"

# Weekdays back from today that the demo covers.
WORKING_DAYS = 20


def run():
	create_attendance()
	create_timesheets()
	create_expense_claim()


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

	plan = [
		("Jean Mukendi", "MBK-W-SUB", "MBK-CC-SUB", None, 8),
		("Alice Kabeya", "MBK-W-SUP", "MBK-CC-BLK", None, 7),
		("Grace Mbuyi", "MBK-W-SUB", "MBK-CC-PLT", excavator, 9),
	]

	for name, wbs, code, asset, hours in plan:
		emp = employee(name)
		if not emp:
			continue
		doc = frappe.new_doc("Timesheet")
		doc.employee = emp
		doc.company = company()
		for offset in (12, 9, 5, 2):
			date = getdate(day(-offset))
			if date.weekday() >= 5:
				continue
			doc.append("time_logs", {
				"activity_type": activity,
				"from_time": "%s 08:00:00" % date,
				"to_time": "%s %02d:00:00" % (date, 8 + hours),
				"hours": hours,
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
	log("timesheets: %d, booked to WBS, cost code and plant" % len(plan))


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
