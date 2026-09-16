# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Tools Outstanding - build sheet head 57, row 40.

Every tool still in someone's hands. This is the list a storeman works from at
demobilisation, so it is ordered by how long the tool has been out: the oldest
outstanding item is the one least likely to come back.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	today = getdate(nowdate())
	rows = get_rows(filters)

	data = []
	for r in rows:
		outstanding_qty = flt(r.qty) - flt(r.returned_qty)
		expected = r.line_expected or r.expected_return_date
		data.append({
			"tool_issue": r.parent,
			"issued_to": r.issued_to,
			"employee_name": r.employee_name,
			"project": r.project,
			"site": r.site,
			"item_code": r.item_code,
			"serial_no": r.serial_no,
			"issue_date": r.issue_date,
			"days_outstanding": date_diff(today, getdate(r.issue_date)) if r.issue_date else 0,
			"qty": outstanding_qty,
			"value": outstanding_qty * flt(r.valuation_rate),
			"expected_return_date": expected,
			"overdue": 1 if expected and getdate(expected) < today else 0,
		})

	if filters.get("only_overdue"):
		data = [r for r in data if r["overdue"]]

	data.sort(key=lambda r: (-r["overdue"], -r["days_outstanding"]))
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "tool_issue", "label": _("Tool Issue"), "fieldtype": "Link",
		 "options": "Tool Issue", "width": 140},
		{"fieldname": "issued_to", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 120},
		{"fieldname": "employee_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link",
		 "options": "Project", "width": 130},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location",
		 "width": 130},
		{"fieldname": "item_code", "label": _("Tool"), "fieldtype": "Link", "options": "Item",
		 "width": 150},
		{"fieldname": "serial_no", "label": _("Serial No"), "fieldtype": "Data", "width": 130},
		{"fieldname": "issue_date", "label": _("Issued"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_outstanding", "label": _("Days Out"), "fieldtype": "Int",
		 "width": 100},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 80},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "expected_return_date", "label": _("Due Back"), "fieldtype": "Date",
		 "width": 100},
		{"fieldname": "overdue", "label": _("Overdue"), "fieldtype": "Check", "width": 90},
	]


def get_rows(filters):
	# docstatus 1 only: a draft issue has not moved any stock, and a cancelled
	# one has moved it back.
	conditions = ["ti.docstatus = 1", "ifnull(item.is_returned, 0) = 0"]
	values = {}
	for key, column in (("project", "ti.project"), ("issued_to", "ti.issued_to"),
	                    ("site", "ti.site"), ("item_code", "item.item_code")):
		if filters.get(key):
			conditions.append("%s = %%(%s)s" % (column, key))
			values[key] = filters[key]

	return frappe.db.sql(
		"""
		select ti.name as parent, ti.issued_to, ti.project, ti.site, ti.issue_date,
		       ti.expected_return_date, emp.employee_name,
		       item.item_code, item.serial_no, item.qty, item.returned_qty,
		       item.valuation_rate, item.expected_return_date as line_expected
		from `tabTool Issue Item` item
		inner join `tabTool Issue` ti on ti.name = item.parent
		left join `tabEmployee` emp on emp.name = ti.issued_to
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)
