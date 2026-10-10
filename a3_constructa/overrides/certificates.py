# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Skills and certificates - catalogue 7.7.

Each employee carries their certificates (Employee Certificate: trade test,
operator licence, work at height ...) with an expiry date. An asset category
can require one (Asset Category.required_certificate) of whoever operates its
machines.

- A daily job tells HR (HR Manager / HR User) and the employee's manager (reports
  to) 30 and then 7 days before a certificate expires, once each; renewing it
  (a new expiry date) starts the reminders again.
- An Equipment Log, and a Daily Site Report's equipment line, warn when the
  operator holds no certificate the machine's category requires that is valid on
  the day.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, formatdate, getdate, today

HR_ROLES = ("HR Manager", "HR User")
REMINDERS = ((7, "reminded_7"), (30, "reminded_30"))


# ---------------------------------------------------------------- validity

def certificates(employee, kind):
	return frappe.get_all("Employee Certificate", filters={"parenttype": "Employee", "parent": employee, "certificate_type": kind},
	                      fields=["certificate_no", "issue_date", "expiry_date"], order_by="expiry_date desc")


def valid(cert, on) -> bool:
	on = getdate(on)
	return (not cert.issue_date or getdate(cert.issue_date) <= on) and (not cert.expiry_date or getdate(cert.expiry_date) >= on)


def operator_problem(asset, operator, on) -> str | None:
	"""Why the operator can't run the machine on the day, or None."""
	if not (asset and operator):
		return None
	category = frappe.db.get_value("Asset", asset, "asset_category")
	kind = frappe.db.get_value("Asset Category", category, "required_certificate") if category else None
	if not kind:
		return None
	held = certificates(operator, kind)
	if any(valid(c, on) for c in held):
		return None
	name = frappe.db.get_value("Employee", operator, "employee_name") or operator
	machine = frappe.db.get_value("Asset", asset, "asset_name") or asset
	if held and held[0].expiry_date and getdate(held[0].expiry_date) < getdate(on):
		return _("{0}'s {1} expired on {2}: {3} ({4}) needs a valid one.").format(
			name, _(kind).lower(), formatdate(held[0].expiry_date, "d MMM yyyy"), machine, category)
	return _("{0} holds no {1}, which {2} ({3}) needs.").format(name, _(kind).lower(), machine, category)


def equipment_log_validate(doc, method=None):
	problem = operator_problem(doc.asset, doc.operator, doc.log_date)
	if problem:
		frappe.msgprint(problem, title=_("Operator certificate"), indicator="orange", alert=True)


def site_report_validate(doc, method=None):
	for row in doc.get("equipment") or []:
		problem = operator_problem(row.asset, row.get("operator"), doc.report_date)
		if problem:
			frappe.msgprint(_("Equipment row {0}: {1}").format(row.idx, problem), title=_("Operator certificate"), indicator="orange", alert=True)


# ---------------------------------------------------------------- reminders

def employee_validate(doc, method=None):
	"""A renewed certificate (new expiry date) gets its reminders again."""
	before = {r.name: r.expiry_date for r in frappe.get_all("Employee Certificate", filters={"parenttype": "Employee", "parent": doc.name},
	                                                       fields=["name", "expiry_date"])} if not doc.is_new() else {}
	for row in doc.get("certificates") or []:
		if row.name in before and str(before[row.name] or "") != str(row.expiry_date or ""):
			row.reminded_30 = row.reminded_7 = 0


def hr_users() -> list[str]:
	return sorted(set(frappe.db.sql_list("""select distinct hr.parent from `tabHas Role` hr join tabUser u on u.name = hr.parent
		where hr.role in %s and hr.parenttype = 'User' and u.enabled = 1 and u.name not in ('Administrator', 'Guest')""", [HR_ROLES])))


def daily():
	"""Certificates expiring within 30, then 7, days: tell HR and the manager, once each."""
	rows = frappe.db.sql("""select c.name, c.parent employee, c.certificate_type, c.certificate_no, c.expiry_date, c.reminded_30, c.reminded_7,
			e.employee_name, e.reports_to, e.status
		from `tabEmployee Certificate` c join tabEmployee e on e.name = c.parent
		where c.parenttype = 'Employee' and c.expiry_date >= %(today)s and c.expiry_date <= date_add(%(today)s, interval 30 day)
			and e.status = 'Active'""", {"today": getdate(today())}, as_dict=True)
	sent = []
	hr = hr_users()
	for r in rows:
		days = date_diff(r.expiry_date, today())
		due = next(((n, field) for n, field in REMINDERS if days <= n and not r[field]), None)
		if not due:
			continue
		n, field = due
		manager = frappe.db.get_value("Employee", r.reports_to, "user_id") if r.reports_to else None
		users = sorted(set(hr + ([manager] if manager else [])))
		subject = _("{0}'s {1} expires in {2} days ({3})").format(r.employee_name, _(r.certificate_type).lower(), days,
		                                                          formatdate(r.expiry_date, "d MMM yyyy"))
		for user in users:
			frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Employee",
			                "document_name": r.employee, "subject": subject,
			                "email_content": _("Certificate {0} ({1}). Renew it before it lapses.").format(r.certificate_no or "-", r.certificate_type)
			                }).insert(ignore_permissions=True)
		# The 7-day reminder makes the 30-day one moot.
		frappe.db.set_value("Employee Certificate", r.name, {"reminded_30": 1, **({"reminded_7": 1} if n == 7 else {})}, update_modified=False)
		sent.append({"employee": r.employee, "certificate": r.certificate_type, "days": days, "users": users})
	return sent
