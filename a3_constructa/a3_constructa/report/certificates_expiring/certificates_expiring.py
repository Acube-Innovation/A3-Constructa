# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Certificates Expiring - catalogue 7.7: what lapses in the next 60 days, and what already has.

One row per certificate of an active employee expiring within the window (60 days
by default), plus the expired ones (unless left out): days left, the employee's
designation, crew and manager, and whether a machine category needs it.
Filters: company, days ahead, certificate type, include expired.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = data(filters)
	return columns(), rows, None, None, summary(rows)


def data(filters):
	now = getdate(today())
	until = add_days(now, cint(filters.get("days") or 60))
	conditions = ["c.parenttype = 'Employee'", "e.status = 'Active'", "c.expiry_date is not null", "c.expiry_date <= %(until)s"]
	values = {"until": until, "now": now}
	if not cint(filters.get("include_expired", 1)):
		conditions.append("c.expiry_date >= %(now)s")
	if filters.get("company"):
		conditions.append("e.company = %(company)s"); values["company"] = filters.company
	if filters.get("certificate_type"):
		conditions.append("c.certificate_type = %(kind)s"); values["kind"] = filters.certificate_type
	permitted = frappe.get_list("Employee", pluck="name", limit_page_length=0)
	if not permitted:
		return []
	values["permitted"] = permitted
	rows = frappe.db.sql(f"""select c.parent employee, e.employee_name, e.designation, c.certificate_type, c.certificate_no, c.issued_by,
			c.expiry_date, e.reports_to, m.employee_name manager,
			(select cr.crew_name from `tabCrew Member` cm join tabCrew cr on cr.name = cm.parent
			 where cm.employee = e.name and cm.is_active = 1 and cr.is_active = 1 limit 1) crew
		from `tabEmployee Certificate` c join tabEmployee e on e.name = c.parent left join tabEmployee m on m.name = e.reports_to
		where {' and '.join(conditions)} and e.name in %(permitted)s
		order by c.expiry_date, e.employee_name""", values, as_dict=True)
	needed = {}
	for cat, kind in frappe.get_all("Asset Category", filters={"required_certificate": ["is", "set"]}, fields=["name", "required_certificate"], as_list=True):
		needed.setdefault(kind, []).append(cat)
	for r in rows:
		r.days_left = date_diff(r.expiry_date, now)
		r.status = _("Expired") if r.days_left < 0 else (_("Expires today") if r.days_left == 0 else _("{0} days").format(r.days_left))
		r.needed_for = ", ".join(needed.get(r.certificate_type, []))
	return rows


def columns():
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Data", "width": 120},
		{"fieldname": "crew", "label": _("Crew"), "fieldtype": "Data", "width": 130},
		{"fieldname": "certificate_type", "label": _("Certificate"), "fieldtype": "Data", "width": 130},
		{"fieldname": "certificate_no", "label": _("No"), "fieldtype": "Data", "width": 110},
		{"fieldname": "expiry_date", "label": _("Expires"), "fieldtype": "Date", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "needed_for", "label": _("Needed For"), "fieldtype": "Data", "width": 140},
		{"fieldname": "manager", "label": _("Manager"), "fieldtype": "Data", "width": 140},
		{"fieldname": "issued_by", "label": _("Issued By"), "fieldtype": "Data", "width": 160},
	]


def summary(rows):
	count = lambda test: sum(1 for r in rows if test(r["days_left"]))  # noqa: E731
	return [
		{"label": _("Expired"), "value": count(lambda d: d < 0), "datatype": "Int", "indicator": "Red"},
		{"label": _("Within 7 days"), "value": count(lambda d: 0 <= d <= 7), "datatype": "Int", "indicator": "Red"},
		{"label": _("Within 30 days"), "value": count(lambda d: 7 < d <= 30), "datatype": "Int", "indicator": "Orange"},
		{"label": _("Within 60 days"), "value": count(lambda d: 30 < d <= 60), "datatype": "Int", "indicator": "Blue"},
	]
