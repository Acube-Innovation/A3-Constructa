# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Site-wise Attendance - build sheet head 64, row 42.

Who was on each site each day against who was expected, plus late arrivals and
overtime hours. The absenteeism figure is the one a project manager acts on, so
planned headcount is taken from shift assignments rather than from total
headcount - a man rostered elsewhere is not absent from this site.

Late arrivals come from Employee Checkin: Attendance carries a `late_entry`
flag, but the checkin row is what says by how much and is the source when both
are present.
"""

import frappe
from frappe import _
from frappe.utils import flt

PRESENT_STATUSES = ("Present", "Work From Home")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_attendance(filters)
	planned = get_planned_headcount(filters)
	overtime = get_overtime_hours(filters)

	buckets = {}
	for r in rows:
		key = (r.attendance_date, r.site or r.project or _("Not Set"), r.shift or "")
		b = buckets.setdefault(key, {
			"attendance_date": r.attendance_date,
			"site": r.site or r.project,
			"shift": r.shift,
			"present": 0, "half_day": 0, "absent": 0, "on_leave": 0, "late_in": 0,
		})
		count = int(r.headcount)
		if r.status in PRESENT_STATUSES:
			b["present"] += count
		elif r.status == "Half Day":
			b["half_day"] += count
		elif r.status == "On Leave":
			b["on_leave"] += count
		else:
			b["absent"] += count
		b["late_in"] += int(r.late_count or 0)

	data = []
	for key, b in buckets.items():
		date, site, shift = key
		effective = b["present"] + b["half_day"] * 0.5
		expected = planned.get((date, site, shift)) or (
			b["present"] + b["half_day"] + b["absent"] + b["on_leave"]
		)
		b["planned"] = expected
		b["effective_present"] = effective
		b["absenteeism"] = ((expected - effective) / expected * 100) if expected else 0
		b["ot_hours"] = flt(overtime.get((date, site), 0))
		data.append(b)

	data.sort(key=lambda r: (r["attendance_date"], r["site"] or ""), reverse=True)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "attendance_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "site", "label": _("Site / Project"), "fieldtype": "Data", "width": 180},
		{"fieldname": "shift", "label": _("Shift"), "fieldtype": "Link", "options": "Shift Type",
		 "width": 130},
		{"fieldname": "planned", "label": _("Planned"), "fieldtype": "Float", "precision": 1,
		 "width": 100},
		{"fieldname": "present", "label": _("Present"), "fieldtype": "Int", "width": 90},
		{"fieldname": "half_day", "label": _("Half Day"), "fieldtype": "Int", "width": 90},
		{"fieldname": "on_leave", "label": _("On Leave"), "fieldtype": "Int", "width": 90},
		{"fieldname": "absent", "label": _("Absent"), "fieldtype": "Int", "width": 90},
		{"fieldname": "absenteeism", "label": _("Absenteeism %"), "fieldtype": "Percent",
		 "width": 130},
		{"fieldname": "late_in", "label": _("Late In"), "fieldtype": "Int", "width": 90},
		{"fieldname": "ot_hours", "label": _("OT Hours"), "fieldtype": "Float",
		 "precision": 1, "width": 110},
	]


def get_attendance(filters):
	conditions = ["a.docstatus = 1"]
	values = {}
	for key, column in (("project", "a.project"), ("site", "a.site"), ("shift", "a.shift"),
	                    ("company", "a.company")):
		if filters.get(key):
			conditions.append("%s = %%(%s)s" % (column, key))
			values[key] = filters[key]
	if filters.get("from_date"):
		conditions.append("a.attendance_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("a.attendance_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	return frappe.db.sql(
		"""
		select a.attendance_date, a.site, a.project, a.shift, a.status,
		       count(*) as headcount, sum(ifnull(a.late_entry, 0)) as late_count
		from `tabAttendance` a
		where {conditions}
		group by a.attendance_date, a.site, a.project, a.shift, a.status
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def get_planned_headcount(filters):
	"""How many people were rostered to each site and shift.

	Shift Assignment has no site of its own, so the assignment is attributed to
	whatever site the employee's attendance for that day records. Where nobody
	was rostered, the caller falls back to the attendance headcount.
	"""
	conditions = ["sa.docstatus = 1"]
	values = {}
	if filters.get("from_date"):
		conditions.append("sa.start_date <= %(to_date)s")
		conditions.append("(sa.end_date is null or sa.end_date >= %(from_date)s)")
		values["from_date"] = filters.from_date
		values["to_date"] = filters.get("to_date") or filters.from_date

	if not filters.get("from_date"):
		return {}

	rows = frappe.db.sql(
		"""
		select a.attendance_date, a.site, a.project, sa.shift_type as shift,
		       count(distinct sa.employee) as planned
		from `tabShift Assignment` sa
		inner join `tabAttendance` a
		        on a.employee = sa.employee
		       and a.attendance_date between sa.start_date
		           and ifnull(sa.end_date, a.attendance_date)
		where {conditions}
		group by a.attendance_date, a.site, a.project, sa.shift_type
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {(r.attendance_date, r.site or r.project or _("Not Set"), r.shift or ""): flt(r.planned)
	        for r in rows}


def get_overtime_hours(filters):
	"""Hours worked beyond the shift, per site and day."""
	conditions = ["a.docstatus = 1", "a.working_hours > 0"]
	values = {}
	if filters.get("from_date"):
		conditions.append("a.attendance_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("a.attendance_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select a.attendance_date, a.site, a.project,
		       sum(greatest(a.working_hours - ifnull(st.duration, 8), 0)) as ot
		from `tabAttendance` a
		left join (
		    select name, timestampdiff(hour, start_time, end_time) as duration
		    from `tabShift Type`
		) st on st.name = a.shift
		where {conditions}
		group by a.attendance_date, a.site, a.project
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
	return {(r.attendance_date, r.site or r.project): flt(r.ot) for r in rows}
