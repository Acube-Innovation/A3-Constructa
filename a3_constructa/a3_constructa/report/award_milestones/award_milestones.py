# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Award Milestones - the programme of every award, one row per milestone.

Status is the milestone's own, except that an unfinished milestone past its
planned end shows as Overdue (the rule the Planning & Budgeting overview uses).
Variance days: for a completed milestone, actual end against planned end; for an
overdue one, how many days late it is so far; otherwise blank. Positive is late.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

STATUSES = ("Not Started", "In Progress", "Overdue", "Completed")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "award", "label": _("Award"), "fieldtype": "Link", "options": "Awarded Quotation", "width": 120},
		{"fieldname": "award_title", "label": _("Award Title"), "fieldtype": "Data", "width": 170},
		{"fieldname": "milestone", "label": _("Milestone"), "fieldtype": "Data", "width": 210},
		{"fieldname": "planned_start", "label": _("Planned Start"), "fieldtype": "Date", "width": 105},
		{"fieldname": "planned_end", "label": _("Planned End"), "fieldtype": "Date", "width": 100},
		{"fieldname": "actual_end", "label": _("Actual End"), "fieldtype": "Date", "width": 100},
		{"fieldname": "weightage", "label": _("Weightage %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "billing_percent", "label": _("Billing %"), "fieldtype": "Percent", "width": 85},
		{"fieldname": "variance_days", "label": _("Variance Days"), "fieldtype": "Int", "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 105},
	]


def get_data(filters):
	conditions = [["Awarded Quotation", "docstatus", "<", 2], ["Awarded Quotation Milestone", "name", "is", "set"]]
	if filters.get("company"):
		conditions.append(["Awarded Quotation", "company", "=", filters.company])
	if filters.get("award"):
		conditions.append(["Awarded Quotation", "name", "=", filters.award])
	child = "`tabAwarded Quotation Milestone`"
	rows = frappe.get_list(
		"Awarded Quotation",
		filters=conditions,
		fields=["name as award", "title as award_title", f"{child}.idx as idx", f"{child}.milestone as milestone",
		        f"{child}.planned_start as planned_start", f"{child}.planned_end as planned_end",
		        f"{child}.actual_end as actual_end", f"{child}.weightage as weightage",
		        f"{child}.billing_percent as billing_percent", f"{child}.status as status"],
		order_by="`tabAwarded Quotation`.name asc",
		limit_page_length=0,
	)
	now = getdate(today())
	data = []
	for r in sorted(rows, key=lambda r: (r.award, r.idx)):
		overdue = r.status != "Completed" and r.planned_end and getdate(r.planned_end) < now
		if r.status == "Completed" and r.actual_end and r.planned_end:
			r.variance_days = date_diff(r.actual_end, r.planned_end)
		elif overdue:
			r.variance_days = date_diff(now, r.planned_end)
		else:
			r.variance_days = None
		r.status = "Overdue" if overdue else (r.status or "Not Started")
		if filters.get("status") and r.status != filters.status:
			continue
		if filters.get("overdue_only") and r.status != "Overdue":
			continue
		data.append(r)
	return data
