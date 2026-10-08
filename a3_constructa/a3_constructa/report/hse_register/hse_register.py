# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""HSE Register - catalogue 6.9.

Three views over a period (12 weeks unless chosen):
- Weekly: toolbox talks and the people briefed, permits issued, and incidents by
  type, week by week (weeks start on Monday);
- Open Permits: every permit still open, with the ones past their validity first;
- Incidents: each incident with its type, severity, status, days lost and open actions.
The summary gives the period's totals and the days since the last lost-time
incident (on any date, not only in the period).
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, get_datetime, getdate, now_datetime, today

TYPES = ("Near miss", "First aid", "Lost time", "Property damage", "Environmental")
VIEWS = ("Weekly", "Open Permits", "Incidents")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.to_date = getdate(filters.get("to_date") or today())
	filters.from_date = getdate(filters.get("from_date") or add_days(filters.to_date, -83))
	view = filters.get("view") or "Weekly"
	talks, permits, incidents = data(filters)
	summary = get_summary(filters, talks, permits, incidents)
	if view == "Open Permits":
		return permit_columns(), permit_rows(permits), None, None, summary
	if view == "Incidents":
		return incident_columns(), incident_rows(incidents), None, None, summary
	rows = weekly_rows(filters, talks, permits, incidents)
	return weekly_columns(), rows, None, weekly_chart(rows), summary


def scope(filters, extra):
	conditions = dict(extra)
	for f in ("company", "project"):
		if filters.get(f):
			conditions[f] = filters[f]
	return conditions


def data(filters):
	period = ["between", [filters.from_date, filters.to_date]]
	talks = frappe.get_list("Toolbox Talk", filters=scope(filters, {"talk_date": period}),
	                        fields=["name", "talk_date", "total_attendance"], limit_page_length=0) \
		if frappe.has_permission("Toolbox Talk", "read") else []
	permits = frappe.get_list("Permit to Work", filters=scope(filters, {}),
	                          fields=["name", "project", "site", "wbs", "permit_type", "status", "valid_from", "valid_to", "issued_to_name",
	                                  "work_description"], limit_page_length=0) \
		if frappe.has_permission("Permit to Work", "read") else []
	incidents = frappe.get_list("Site Incident", filters=scope(filters, {}),
	                            fields=["name", "project", "site", "occurred_on", "incident_type", "severity", "status", "days_lost",
	                                    "description"], order_by="occurred_on desc", limit_page_length=0)
	return talks, permits, incidents


def in_period(filters, value):
	return value and filters.from_date <= getdate(value) <= filters.to_date


def week_start(value):
	d = getdate(value)
	return add_days(d, -d.weekday())


# ---------------------------------------------------------------- weekly

def weekly_rows(filters, talks, permits, incidents):
	weeks = OrderedDict()
	cursor = week_start(filters.from_date)
	while cursor <= filters.to_date:
		weeks[cursor] = {"week": cursor, "talks": 0, "attendance": 0, "permits": 0, **{key(t): 0 for t in TYPES}, "incidents": 0}
		cursor = add_days(cursor, 7)
	for t in talks:
		w = weeks.get(week_start(t.talk_date))
		if w:
			w["talks"] += 1
			w["attendance"] += cint(t.total_attendance)
	for p in permits:
		if in_period(filters, p.valid_from):
			w = weeks.get(week_start(p.valid_from))
			if w:
				w["permits"] += 1
	for i in incidents:
		if in_period(filters, i.occurred_on):
			w = weeks.get(week_start(i.occurred_on))
			if w:
				w[key(i.incident_type)] += 1
				w["incidents"] += 1
	return list(weeks.values())


def key(incident_type):
	return incident_type.lower().replace(" ", "_")


def weekly_columns():
	cols = [
		{"fieldname": "week", "label": _("Week of"), "fieldtype": "Date", "width": 110},
		{"fieldname": "talks", "label": _("Toolbox Talks"), "fieldtype": "Int", "width": 110},
		{"fieldname": "attendance", "label": _("People Briefed"), "fieldtype": "Int", "width": 115},
		{"fieldname": "permits", "label": _("Permits Issued"), "fieldtype": "Int", "width": 115},
	]
	cols += [{"fieldname": key(t), "label": _(t), "fieldtype": "Int", "width": 115} for t in TYPES]
	cols.append({"fieldname": "incidents", "label": _("Incidents"), "fieldtype": "Int", "width": 90})
	return cols


def weekly_chart(rows):
	return {
		"data": {
			"labels": [getdate(r["week"]).strftime("%d %b") for r in rows],
			"datasets": [
				{"name": _("Toolbox talks"), "values": [r["talks"] for r in rows]},
				{"name": _("Incidents"), "values": [r["incidents"] for r in rows]},
			],
		},
		"type": "bar",
		"colors": ["#3a6ea5", "#c2452d"],
	}


# ---------------------------------------------------------------- open permits

def permit_columns():
	return [
		{"fieldname": "permit", "label": _("Permit"), "fieldtype": "Link", "options": "Permit to Work", "width": 140},
		{"fieldname": "permit_type", "label": _("Type"), "fieldtype": "Data", "width": 140},
		{"fieldname": "work", "label": _("Work"), "fieldtype": "Data", "width": 260},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 110},
		{"fieldname": "issued_to", "label": _("Issued To"), "fieldtype": "Data", "width": 150},
		{"fieldname": "valid_to", "label": _("Valid To"), "fieldtype": "Datetime", "width": 160},
		{"fieldname": "state", "label": _("State"), "fieldtype": "Data", "width": 160},
	]


def permit_rows(permits):
	now = now_datetime()
	rows = []
	for p in permits:
		if p.status != "Open":
			continue
		expired = get_datetime(p.valid_to) < now
		hours = (now - get_datetime(p.valid_to)).total_seconds() / 3600
		rows.append({"permit": p.name, "permit_type": _(p.permit_type), "work": p.work_description, "project": p.project, "wbs": p.wbs,
		             "issued_to": p.issued_to_name, "valid_to": p.valid_to, "expired": int(expired),
		             "state": _("Expired {0} h ago").format(int(hours)) if expired else _("Valid")})
	return sorted(rows, key=lambda r: (-r["expired"], r["valid_to"]))


# ---------------------------------------------------------------- incidents

def incident_columns():
	return [
		{"fieldname": "incident", "label": _("Incident"), "fieldtype": "Link", "options": "Site Incident", "width": 140},
		{"fieldname": "occurred_on", "label": _("Occurred On"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "incident_type", "label": _("Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "severity", "label": _("Severity"), "fieldtype": "Data", "width": 90},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "days_lost", "label": _("Days Lost"), "fieldtype": "Int", "width": 90},
		{"fieldname": "open_actions", "label": _("Open Actions"), "fieldtype": "Int", "width": 105},
		{"fieldname": "description", "label": _("What Happened"), "fieldtype": "Data", "width": 320},
	]


def incident_rows(incidents):
	names = [i.name for i in incidents]
	open_actions = {}
	for row in frappe.get_all("Incident Action", filters={"parenttype": "Site Incident", "parent": ["in", names or [""]], "done": 0},
	                          fields=["parent"]):
		open_actions[row.parent] = open_actions.get(row.parent, 0) + 1
	return [{"incident": i.name, "occurred_on": i.occurred_on, "incident_type": _(i.incident_type), "severity": _(i.severity),
	         "project": i.project, "status": _(i.status), "days_lost": i.days_lost, "open_actions": open_actions.get(i.name, 0),
	         "description": i.description} for i in incidents]


# ---------------------------------------------------------------- summary

def get_summary(filters, talks, permits, incidents):
	now = now_datetime()
	open_permits = [p for p in permits if p.status == "Open"]
	expired = [p for p in open_permits if get_datetime(p.valid_to) < now]
	in_period_incidents = [i for i in incidents if in_period(filters, i.occurred_on)]
	lost_time = [i for i in incidents if i.incident_type == "Lost time"]
	last = max((getdate(i.occurred_on) for i in lost_time), default=None)
	return [
		{"label": _("Toolbox talks"), "value": len(talks), "datatype": "Int", "indicator": "Blue"},
		{"label": _("People briefed"), "value": sum(cint(t.total_attendance) for t in talks), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Open permits"), "value": len(open_permits), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Expired, still open"), "value": len(expired), "datatype": "Int", "indicator": "Red" if expired else "Green"},
		{"label": _("Incidents"), "value": len(in_period_incidents), "datatype": "Int", "indicator": "Orange" if in_period_incidents else "Green"},
		{"label": _("Days without a lost-time incident"), "value": date_diff(today(), last) if last else _("None on record"),
		 "datatype": "Int" if last else "Data", "indicator": "Green"},
	]
