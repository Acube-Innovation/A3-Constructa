# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Overdue RFIs - catalogue 6.10.

Open RFIs whose answer was required by a date now past, the longest overdue
first: who must answer, how many days late, how long open, and the WBS and
drawing they hold up. "Due within" adds those falling due in the next few days.
The summary also counts answered RFIs with a cost or time impact whose change
event has not been raised yet.

Filters: company, project, who must answer, due within (days).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	now = getdate(today())
	horizon = add_days(now, cint(filters.get("due_within")))
	conditions = {"status": "Open", "required_by": ["<=", horizon] if cint(filters.get("due_within")) else ["<", now]}
	for f in ("company", "project"):
		if filters.get(f):
			conditions[f] = filters[f]
	if filters.get("addressed_to"):
		conditions["addressed_to"] = ["like", f"%{filters.addressed_to}%"]
	rfis = frappe.get_list("RFI", filters=conditions,
	                       fields=["name", "subject", "project", "wbs", "drawing", "addressed_to", "raised_on", "required_by", "raised_by"],
	                       order_by="required_by asc, raised_on asc", limit_page_length=0)
	rows = [{
		"rfi": r.name, "subject": r.subject, "project": r.project, "wbs": r.wbs, "drawing": r.drawing, "addressed_to": r.addressed_to,
		"raised_on": r.raised_on, "required_by": r.required_by, "days_overdue": max(0, date_diff(now, r.required_by)),
		"days_open": date_diff(now, r.raised_on), "raised_by": frappe.utils.get_fullname(r.raised_by) if r.raised_by else None,
		"overdue": int(getdate(r.required_by) < now),
	} for r in rfis]
	return get_columns(), rows, None, None, get_summary(filters, rows, now)


def get_columns():
	return [
		{"fieldname": "rfi", "label": _("RFI"), "fieldtype": "Link", "options": "RFI", "width": 140},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 260},
		{"fieldname": "addressed_to", "label": _("Waiting On"), "fieldtype": "Data", "width": 190},
		{"fieldname": "required_by", "label": _("Required By"), "fieldtype": "Date", "width": 105},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 105},
		{"fieldname": "days_open", "label": _("Days Open"), "fieldtype": "Int", "width": 90},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 110},
		{"fieldname": "drawing", "label": _("Drawing"), "fieldtype": "Link", "options": "Drawing Register", "width": 130},
		{"fieldname": "raised_by", "label": _("Raised By"), "fieldtype": "Data", "width": 140},
	]


def get_summary(filters, rows, now):
	scope = {f: filters[f] for f in ("company", "project") if filters.get(f)}
	open_count = len(frappe.get_list("RFI", filters={**scope, "status": "Open"}, pluck="name", limit_page_length=0))
	no_ce = frappe.get_list("RFI", filters={**scope, "status": ["!=", "Open"], "change_event": ["is", "not set"]},
	                        or_filters={"cost_impact": 1, "time_impact": 1}, pluck="name", limit_page_length=0)
	overdue = [r for r in rows if r["overdue"]]
	return [
		{"label": _("Open RFIs"), "value": open_count, "datatype": "Int", "indicator": "Blue"},
		{"label": _("Overdue"), "value": len(overdue), "datatype": "Int", "indicator": "Red" if overdue else "Green"},
		{"label": _("Longest overdue (days)"), "value": max((r["days_overdue"] for r in overdue), default=0), "datatype": "Int",
		 "indicator": "Red" if overdue else "Grey"},
		{"label": _("Cost or time impact, no change event"), "value": len(no_ce), "datatype": "Int",
		 "indicator": "Orange" if no_ce else "Grey"},
	]
