# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Baseline Variance - catalogue 6.4: the programme against its baseline.

Tasks: baseline, current (expected) and actual dates, start and finish variance in
days (positive is late), and the revision the baseline comes from with its reason.
By default each task is compared with its current baseline; "Against revision"
compares with an earlier revision's snapshot instead. WBS: the same rolled up the
tree, the latest baseline and current finish under each node and its worst task.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

from a3_constructa.overrides.task_baseline import current_dates, wbs_variance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("project"):
		return [], [], _("Choose a project to compare its programme with the baseline.")
	if (filters.get("view") or "Tasks") == "WBS":
		data = wbs_rows(filters)
		return wbs_columns(), data, None, None, summary(data, "worst", _("WBS nodes late"))
	data = task_rows(filters)
	return task_columns(), data, None, None, summary(data, "finish_variance", _("Tasks finishing late"))


def task_columns():
	date = {"fieldtype": "Date", "width": 100}
	return [
		{"fieldname": "task", "label": _("Task"), "fieldtype": "Link", "options": "Task", "width": 125},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 220},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 105},
		{"fieldname": "baseline_start", "label": _("Baseline Start"), **date},
		{"fieldname": "baseline_end", "label": _("Baseline End"), **date},
		{"fieldname": "current_start", "label": _("Current Start"), **date},
		{"fieldname": "current_end", "label": _("Current End"), **date},
		{"fieldname": "actual_end", "label": _("Actual End"), **date},
		{"fieldname": "start_variance", "label": _("Start Var. (d)"), "fieldtype": "Int", "width": 105},
		{"fieldname": "finish_variance", "label": _("Finish Var. (d)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "revision", "label": _("Revision"), "fieldtype": "Int", "width": 80},
		{"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 260},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
	]


def reasons(project):
	return {r.revision_no: r.reason for r in frappe.get_all("Schedule Revision", filters={"project": project, "docstatus": 1},
	                                                        fields=["revision_no", "reason"])}


def subtree(wbs):
	lft, rgt = frappe.db.get_value("WBS", wbs, ["lft", "rgt"])
	return frappe.get_all("WBS", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")


def task_rows(filters):
	conditions = {"project": filters.project, "is_template": 0, "status": ["!=", "Cancelled"], "is_group": 0}
	if filters.get("wbs"):
		conditions["wbs"] = ["in", subtree(filters.wbs)]
	tasks = frappe.get_list("Task", filters=conditions, order_by="exp_start_date asc, name asc", limit_page_length=0,
	                        fields=["name", "subject", "wbs", "exp_start_date", "exp_end_date", "act_start_date", "act_end_date", "completed_on",
	                                "baseline_start", "baseline_end", "baseline_revision", "status"])
	why = reasons(filters.project)
	snapshot, revision_no = {}, None
	if filters.get("revision"):
		revision_no = frappe.db.get_value("Schedule Revision", filters.revision, "revision_no")
		snapshot = {r.task: r for r in frappe.get_all("Schedule Revision Task", filters={"parent": filters.revision}, fields=["task", "start", "end"])}
	data = []
	for t in tasks:
		if snapshot:
			base = snapshot.get(t.name)
			b_start, b_end, rev = (base.start, base.end, revision_no) if base else (None, None, None)
		else:
			b_start, b_end, rev = t.baseline_start, t.baseline_end, t.baseline_revision if t.baseline_end else None
		start, end = current_dates(t)
		data.append({"task": t.name, "subject": t.subject, "wbs": t.wbs, "baseline_start": b_start, "baseline_end": b_end,
		             "current_start": t.exp_start_date, "current_end": t.exp_end_date, "actual_end": (t.act_end_date or t.completed_on) if t.status == "Completed" else None,
		             "start_variance": (getdate(start) - getdate(b_start)).days if b_start and start else None,
		             "finish_variance": (getdate(end) - getdate(b_end)).days if b_end and end else None,
		             "revision": rev, "reason": why.get(rev) if rev is not None else _("Not baselined"), "status": _(t.status)})
	return data


def wbs_columns():
	return [
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 120},
		{"fieldname": "wbs_name", "label": _("Name"), "fieldtype": "Data", "width": 230},
		{"fieldname": "tasks", "label": _("Tasks"), "fieldtype": "Int", "width": 70},
		{"fieldname": "baseline_finish", "label": _("Baseline Finish"), "fieldtype": "Date", "width": 115},
		{"fieldname": "current_finish", "label": _("Current Finish"), "fieldtype": "Date", "width": 115},
		{"fieldname": "finish_change", "label": _("Finish Moved (d)"), "fieldtype": "Int", "width": 120},
		{"fieldname": "worst", "label": _("Worst Task (d)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "late", "label": _("Tasks Late"), "fieldtype": "Int", "width": 90},
	]


def wbs_rows(filters):
	rolled = wbs_variance(filters.project)
	keep = set(subtree(filters.wbs)) if filters.get("wbs") else None
	rows = [{"wbs": node, **agg} for node, agg in rolled.items() if keep is None or node in keep]
	rows.sort(key=lambda r: r["lft"])
	for r in rows:
		r.pop("lft", None)
	return rows


def summary(data, field, label):
	late = [r for r in data if cint(r.get(field)) > 0]
	worst = max((cint(r.get(field)) for r in data if r.get(field) is not None), default=0)
	return [{"label": label, "value": len(late), "datatype": "Int", "indicator": "Red" if late else "Green"},
	        {"label": _("Worst (days)"), "value": worst, "datatype": "Int"}]
