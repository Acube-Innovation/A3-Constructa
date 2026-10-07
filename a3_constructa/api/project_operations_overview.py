# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Project Operations Overview" tab of the Project Operations workspace.

Same contract as the other overviews: one call, every figure through
`frappe.get_list` (scoped to the user's default company: by company, or by the
company's projects), a section the caller cannot read comes back `restricted`.

- Headline: % complete against % planned (the WBS roll-up, P-06D), across the
  open projects, weighted by budget.
- KPIs: tasks starting this week and how many are Ready (look-ahead, P-06E); open
  NCRs; open snags.
- Checks: critical tasks late, sites with no Daily Site Report yesterday,
  look-ahead constraints open, NCRs overdue, snags past due.
- Beside them: critical tasks in the next 7 days.
- Breakdowns: tasks by status and delay hours by cause (30 days); open NCRs by
  WBS and open snags by trade; labour hours on site per week.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime, today

from a3_constructa.api import finance_accounting_overview as fa
from a3_constructa.api.utils import default_company, default_currency

DOCTYPES = ("Task", "Project", "Daily Site Report", "Non Conformance", "Snag List", "WBS")
OPEN_TASK = ("Completed", "Cancelled", "Template")
TASK_STATUSES = ("Open", "Working", "Pending Review", "Overdue", "Completed")
WEEKS = 12


def _can_read(doctype):
	return bool(frappe.db.exists("DocType", doctype)) and frappe.has_permission(doctype, "read")


def _list(doctype, filters=None, **kwargs):
	return frappe.get_list(doctype, filters=fa._scoped(doctype, filters), limit_page_length=0, **kwargs)


def _listed(doctype, filters: dict) -> dict:
	"""List-view filters reproducing a count: the filters plus the company (or its projects)."""
	company = default_company()
	if not company:
		return dict(filters)
	if frappe.get_meta(doctype).has_field("company"):
		return {**filters, "company": company}
	if frappe.get_meta(doctype).has_field("project"):
		return {**filters, "project": ["in", _projects()]}
	return dict(filters)


def _projects() -> list[str]:
	return [p.name for p in _list("Project", {"status": "Open"}, fields=["name"])] if _can_read("Project") else []


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	readable = {d for d in DOCTYPES if _can_read(d)}
	tasks = _tasks(readable)
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"progress": _progress(readable, now),
		"week": _week(readable, now),
		"ncrs": _ncrs(readable, now),
		"snags": _snags(readable, now),
		"tasks": _task_summary(tasks),
		"delays": _delays(readable, now),
		"critical": _critical(tasks, now),
		"labour": _labour(readable, now),
		"health": _health(readable, now, tasks),
	}


# ---------------------------------------------------------------- sources

def _tasks(readable):
	if "Task" not in readable:
		return None
	return _list("Task", {"is_template": 0, "is_group": 0}, fields=["name", "subject", "project", "status", "is_critical", "is_milestone",
	                                                               "exp_start_date", "exp_end_date", "progress", "wbs", "forecast_end",
	                                                               "total_float_days"])


def critically_late(t, now) -> int:
	"""Days a task is driving the finish late: on the critical path and past its planned
	finish, or forecast (P-06D) to finish later than planned by more than its float."""
	if t.status in OPEN_TASK or t.is_milestone or not t.exp_end_date:
		return 0
	end = getdate(t.exp_end_date)
	forecast = max(getdate(t.forecast_end), now) if t.forecast_end else max(end, now)
	slip = (forecast - end).days
	if t.is_critical:
		return max(slip, 0)
	if t.total_float_days is None:
		return 0
	return max(slip - int(t.total_float_days), 0)


def _project_names(names):
	names = [n for n in set(names) if n]
	if not names or not _can_read("Project"):
		return {}
	return {p.name: p.project_name for p in frappe.get_list("Project", filters={"name": ["in", names]}, fields=["name", "project_name"],
	                                                        limit_page_length=0)}


# ---------------------------------------------------------------- sections

def _progress(readable, now):
	if not {"WBS", "Task", "Project"} <= readable:
		return {"restricted": True}
	from a3_constructa.overrides.task_progress import wbs_progress

	rows = []
	for project in _projects():
		nodes = wbs_progress(project, now)
		roots = [n for n in nodes.values() if not n["parent"] or n["parent"] not in nodes]
		if not roots or not any(r["measured"] for r in roots):
			continue
		budget = sum(flt(r["budget"]) for r in roots)
		percent = sum(flt(r["budget"]) * r["percent"] for r in roots) / budget if budget else sum(r["percent"] for r in roots) / len(roots)
		planned = sum(flt(r["budget"]) * r["planned"] for r in roots) / budget if budget else sum(r["planned"] for r in roots) / len(roots)
		rows.append({"project": project, "budget": budget, "percent": flt(percent, 1), "planned": flt(planned, 1)})
	names = _project_names([r["project"] for r in rows])
	for r in rows:
		r["label"] = names.get(r["project"]) or r["project"]
	total = sum(r["budget"] for r in rows)
	weigh = lambda key: flt(sum(r["budget"] * r[key] for r in rows) / total, 1) if total else (  # noqa: E731
		flt(sum(r[key] for r in rows) / len(rows), 1) if rows else 0)
	return {"restricted": False, "percent": weigh("percent"), "planned": weigh("planned"),
	        "projects": sorted(rows, key=lambda r: -r["budget"])}


def _week(readable, now):
	"""Tasks starting this week, and how many the look-ahead finds Ready."""
	if "Task" not in readable:
		return {"restricted": True}
	from a3_constructa.a3_constructa.report.three_week_look_ahead.three_week_look_ahead import look_ahead

	monday = add_days(now, -now.weekday())
	sunday = add_days(monday, 6)
	rows = [r for r in look_ahead(frappe._dict(company=default_company())) if r["project"] in set(_projects())]
	starting = [r for r in rows if getdate(monday) <= getdate(r["start"]) <= getdate(sunday)]
	blocked = [r for r in rows if r["ready"] != _("Ready")]
	return {"restricted": False, "starting": len(starting), "ready": sum(1 for r in starting if r["ready"] == _("Ready")),
	        "monday": monday, "sunday": sunday, "in_window": len(rows), "blocked": [r["task"] for r in blocked],
	        "starting_tasks": [r["task"] for r in starting]}


def _ncrs(readable, now):
	if "Non Conformance" not in readable:
		return {"restricted": True}
	rows = _list("Non Conformance", {"status": ["!=", "Closed"]}, fields=["name", "wbs", "due_date", "cost_impact", "status"])
	by = defaultdict(lambda: {"count": 0, "amount": 0.0})
	for r in rows:
		by[r.wbs]["count"] += 1
		by[r.wbs]["amount"] += flt(r.cost_impact)
	names = {w.name: w.wbs_name for w in frappe.get_list("WBS", filters={"name": ["in", [k for k in by if k] or [""]]}, fields=["name", "wbs_name"])} \
		if "WBS" in readable else {}
	return {"restricted": False, "open": len(rows), "overdue": sum(1 for r in rows if r.due_date and getdate(r.due_date) < now),
	        "cost": sum(flt(r.cost_impact) for r in rows),
	        "by_wbs": fa._top([{"label": f"{k} · {names.get(k, '')}" if k else _("No WBS"), "value": k, **v} for k, v in by.items()], 6),
	        "filters": _listed("Non Conformance", {"status": ["!=", "Closed"]})}


def _snag_items(readable):
	if "Snag List" not in readable:
		return None
	lists = {l.name: l for l in _list("Snag List", fields=["name", "project"])}
	if not lists:
		return []
	return frappe.get_all("Snag Item", filters={"parenttype": "Snag List", "parent": ["in", list(lists)]},
	                      fields=["parent", "trade", "status", "due_date"])


def _snags(readable, now):
	items = _snag_items(readable)
	if items is None:
		return {"restricted": True}
	open_items = [i for i in items if i.status != "Verified"]
	by = defaultdict(lambda: {"count": 0, "lists": set()})
	for i in open_items:
		by[i.trade or _("Unassigned")]["count"] += 1
		by[i.trade or _("Unassigned")]["lists"].add(i.parent)
	return {"restricted": False, "open": sum(1 for i in open_items if i.status == "Open"), "fixed": sum(1 for i in open_items if i.status == "Fixed"),
	        "past_due": [i for i in open_items if i.due_date and getdate(i.due_date) < now],
	        "by_trade": sorted([{"label": k, "value": ["in", sorted(v["lists"])], "count": v["count"]} for k, v in by.items()], key=lambda r: -r["count"]),
	        "filters": {}}


def _task_summary(tasks):
	if tasks is None:
		return {"restricted": True}
	rows = [t for t in tasks if t.project in set(_projects()) and not t.is_milestone]
	by = []
	for status in TASK_STATUSES:
		n = sum(1 for t in rows if t.status == status)
		if n:
			by.append({"label": _(status), "value": status, "count": n})
	return {"restricted": False, "by_status": by, "total": sum(r["count"] for r in by),
	        "filters": _listed("Task", {"is_template": 0, "is_group": 0, "is_milestone": 0, "project": ["in", _projects()]})}


def _delays(readable, now):
	if "Daily Site Report" not in readable:
		return {"restricted": True}
	start = add_days(now, -30)
	reports = {r.name for r in _list("Daily Site Report", {"docstatus": 1, "report_date": [">=", str(start)]}, fields=["name"])}
	rows = frappe.get_all("DSR Delay", filters={"parenttype": "Daily Site Report", "parent": ["in", list(reports) or [""]]},
	                      fields=["parent", "cause", "hours_lost"]) if reports else []
	by = defaultdict(lambda: {"amount": 0.0, "count": 0, "reports": set()})
	for r in rows:
		by[r.cause]["amount"] += flt(r.hours_lost); by[r.cause]["count"] += 1; by[r.cause]["reports"].add(r.parent)
	return {"restricted": False, "hours": sum(flt(r.hours_lost) for r in rows), "reports": len(reports),
	        "by_cause": sorted([{"label": _(k), "value": ["in", sorted(v["reports"])], "count": v["count"], "amount": flt(v["amount"], 1)}
	                            for k, v in by.items()], key=lambda r: -r["amount"])}


def _critical(tasks, now):
	"""Critical (or critically late) tasks running or starting in the next 7 days."""
	if tasks is None:
		return {"restricted": True}
	until = add_days(now, 7)
	projects = set(_projects())
	rows = [t for t in tasks if (t.is_critical or critically_late(t, now)) and t.project in projects and t.status not in OPEN_TASK
	        and not t.is_milestone and t.exp_start_date and getdate(t.exp_start_date) <= until]
	names = _project_names([t.project for t in rows])
	rows.sort(key=lambda t: (-critically_late(t, now), getdate(t.exp_start_date), t.name))
	return {"restricted": False, "list": [{"name": t.name, "subject": t.subject, "project": names.get(t.project) or t.project,
	                                       "start": t.exp_start_date, "end": t.exp_end_date, "forecast": t.forecast_end,
	                                       "progress": flt(t.progress), "late": critically_late(t, now),
	                                       "starting": getdate(t.exp_start_date) > now} for t in rows]}


def _labour(readable, now):
	"""Labour hours (with overtime) and hours lost on the filed site reports, per week."""
	if "Daily Site Report" not in readable:
		return {"restricted": True}
	monday = getdate(add_days(now, -now.weekday()))
	start = add_days(monday, -7 * (WEEKS - 1))
	weeks = [{"week": str(add_days(start, 7 * i)), "label": add_days(start, 7 * i).strftime("%d %b"), "hours": 0.0, "lost": 0.0, "reports": 0}
	         for i in range(WEEKS)]
	index = {w["week"]: w for w in weeks}
	for r in _list("Daily Site Report", {"docstatus": 1, "report_date": [">=", str(start)]},
	               fields=["report_date", "total_hours", "total_overtime_hours", "hours_lost"]):
		d = getdate(r.report_date)
		w = index.get(str(add_days(d, -d.weekday())))
		if w:
			w["hours"] += flt(r.total_hours) + flt(r.total_overtime_hours); w["lost"] += flt(r.hours_lost); w["reports"] += 1
	return {"restricted": False, "weeks": weeks}


# ---------------------------------------------------------------- checks

def _health(readable, now, tasks) -> list[dict]:
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append({"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta})

	projects = _projects()
	late = [t for t in tasks or [] if t.project in set(projects) and critically_late(t, now)]
	check("Critical tasks late", "critical", "Task", len(late) if tasks is not None else None,
	      {"name": ["in", [t.name for t in late]]},
	      _("Late beyond their float: they move the finish") if late else _("Critical path, or forecast past planned + float"))

	missing = None
	if {"Daily Site Report", "Task", "Project"} <= readable:
		yesterday = add_days(now, -1)
		running = {t.project for t in tasks or [] if t.project in set(projects) and t.status not in OPEN_TASK and not t.is_milestone
		           and t.exp_start_date and getdate(t.exp_start_date) <= getdate(yesterday)}
		filed = {r.project for r in _list("Daily Site Report", {"report_date": str(yesterday), "docstatus": ["<", 2]}, fields=["project"])}
		missing = sorted(p for p in running if p not in filed and frappe.db.get_value("Project", p, "location"))
	check("Sites with no Daily Site Report yesterday", "warning", "Project", len(missing) if missing is not None else None,
	      {"name": ["in", missing or []]}, _("Work was planned there but nothing was filed"))

	week = _week(readable, now)
	blocked = None if week.get("restricted") else week["blocked"]
	check("Look-ahead constraints open", "warning", "Task", len(blocked) if blocked is not None else None,
	      {"name": ["in", blocked or []]}, _("Tasks in the next three weeks that aren't Ready"))

	overdue = {"status": ["!=", "Closed"], "due_date": ["<", str(now)]}
	rows = _list("Non Conformance", overdue, fields=["name"]) if "Non Conformance" in readable else None
	check("NCRs past their due date", "critical", "Non Conformance", len(rows) if rows is not None else None, _listed("Non Conformance", overdue),
	      _("Corrective action is late"))

	snags = _snags(readable, now)
	past = None if snags.get("restricted") else snags["past_due"]
	check("Snags past their due date", "warning", "Snag List", len(past) if past is not None else None,
	      {"name": ["in", sorted({i.parent for i in past or []})]}, _("Open or fixed, not verified, and past due"))

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
