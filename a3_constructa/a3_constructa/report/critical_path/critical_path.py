# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Critical Path - catalogue 6.2: the project's critical tasks (no float) in date
order, with their WBS, total float and predecessors (type and lag). "All tasks"
lists the rest too, so the float of every task can be read."""

import frappe
from frappe import _
from frappe.utils import cint, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("project"):
		return get_columns(), []
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data, filters)


def get_columns():
	return [
		{"fieldname": "task", "label": _("Task"), "fieldtype": "Link", "options": "Task", "width": 130},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 230},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 110},
		{"fieldname": "exp_start_date", "label": _("Start"), "fieldtype": "Date", "width": 100},
		{"fieldname": "exp_end_date", "label": _("End"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days", "label": _("Days"), "fieldtype": "Int", "width": 65},
		{"fieldname": "total_float_days", "label": _("Float"), "fieldtype": "Int", "width": 70},
		{"fieldname": "predecessors", "label": _("Predecessors"), "fieldtype": "Data", "width": 260},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "progress", "label": _("Progress %"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "foreman_name", "label": _("Foreman"), "fieldtype": "Data", "width": 140},
	]


def get_data(filters):
	conditions = {"project": filters.project, "is_group": 0, "is_template": 0, "status": ["!=", "Cancelled"], "exp_start_date": ["is", "set"]}
	if not cint(filters.get("show_all")):
		conditions["is_critical"] = 1
	if filters.get("wbs"):
		lft, rgt = frappe.db.get_value("WBS", filters.wbs, ["lft", "rgt"])
		conditions["wbs"] = ["in", frappe.get_all("WBS", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")]
	tasks = frappe.get_list("Task", filters=conditions, order_by="exp_start_date asc, exp_end_date asc",
	                        fields=["name", "subject", "wbs", "exp_start_date", "exp_end_date", "total_float_days", "status", "progress",
	                                "foreman_name", "is_milestone"], limit_page_length=0)
	subjects = dict(frappe.get_all("Task", filters={"project": filters.project}, fields=["name", "subject"], as_list=True))
	data = []
	for t in tasks:
		links = frappe.get_all("Task Depends On", filters={"parent": t.name, "parenttype": "Task"}, fields=["task", "dependency_type", "lag_days"],
		                       order_by="idx")
		preds = []
		for l in links:
			lag = cint(l.lag_days)
			preds.append(f"{subjects.get(l.task, l.task)} ({l.dependency_type or 'FS'}{f' {lag:+d}d' if lag else ''})")
		data.append({"task": t.name, "subject": t.subject, "wbs": t.wbs, "exp_start_date": t.exp_start_date, "exp_end_date": t.exp_end_date,
		             "days": 0 if t.is_milestone else (getdate(t.exp_end_date) - getdate(t.exp_start_date)).days + 1,
		             "total_float_days": t.total_float_days, "predecessors": "; ".join(preds), "status": _(t.status), "progress": t.progress,
		             "foreman_name": t.foreman_name})
	return data


def get_summary(data, filters):
	critical = [r for r in data if cint(r["total_float_days"]) <= 0]
	finish = frappe.db.sql("""select max(exp_end_date) from `tabTask` where project = %s and status != 'Cancelled'""", filters.project)[0][0]
	return [
		{"label": _("Critical tasks"), "value": len(critical), "datatype": "Int", "indicator": "Red" if critical else "Green"},
		{"label": _("Planned finish"), "value": frappe.format(finish, {"fieldtype": "Date"}) if finish else "—", "datatype": "Data"},
	]
