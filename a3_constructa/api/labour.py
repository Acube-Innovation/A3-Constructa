# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 7.5, 7.6 and 13.5: what the crews produce, and how many people are on site.

Weeks run Monday to Sunday. A worker's trade is the trade of their active crew;
someone in two crews takes, for hours on a task, the crew on that task (its
resources or its site reports), and otherwise the skilled trade over general
labour ("Unassigned" when in no crew).

Productivity (per trade, WBS and week):
- quantity done: the tasks' progress log for the week. Once Daily Site Reports
  measure a task in a week, their quantities are that week's measure (a
  quantity typed on the task the same week is left out, not counted twice);
- crew hours: timesheet hours booked to those tasks that week, by trade;
- planned hours for that quantity: quantity × the planned man-hours a unit,
  taken from the Estimate Sheet labour row of the task's BOQ line (gang size ×
  hours a day ÷ output a day), else from the task's crew (headcount × hours a
  day ÷ its standard output);
- productivity factor = planned hours ÷ actual hours, flagged below 0.85.

Headcount (per trade and week, the busiest day of the week):
- planned: the labour on the tasks' resources (P-06B's resource loading);
- actual: workers marked present on the project (Attendance), plus the
  subcontractors' headcount reported on the Daily Site Reports.
"""

import re
from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate

from a3_constructa.a3_constructa.doctype.crew.crew import standard_hours
from a3_constructa.overrides.task_resources import TRADE_WORDS, estimate_for, guess

FLAG_BELOW = 0.85
PRESENT = ("Present", "Half Day", "Work From Home")


def monday(day):
	day = getdate(day)
	return day - timedelta(days=day.weekday())


def crews_of_employees():
	"""{employee: [(crew, trade)]}, skilled trades before general labour."""
	out = defaultdict(list)
	for row in frappe.db.sql("""select m.employee, c.name crew, c.trade from `tabCrew Member` m join `tabCrew` c on c.name = m.parent
		where m.is_active = 1 and c.is_active = 1 order by (c.trade = 'General labour'), c.name""", as_dict=True):
		out[row.employee].append((row.crew, row.trade))
	return out


def trades_of_employees():
	"""{employee: trade}: the skilled trade where a worker is in two crews."""
	return {emp: crews[0][1] for emp, crews in crews_of_employees().items()}


def crews_on_tasks(tasks):
	"""{task: {crew}} from the tasks' labour resources and the site reports' labour lines."""
	out = defaultdict(set)
	if not tasks:
		return out
	for row in frappe.get_all("Task Resource", filters={"parent": ["in", list(tasks)], "parenttype": "Task", "crew": ["is", "set"]},
	                          fields=["parent", "crew"]):
		out[row.parent].add(row.crew)
	for row in frappe.get_all("DSR Labour", filters={"task": ["in", list(tasks)], "crew": ["is", "set"]}, fields=["task", "crew"]):
		out[row.task].add(row.crew)
	return out


def trade_name(text):
	"""A subcontractor's trade as written on the site report, in the crews' terms where it matches."""
	options = (frappe.get_meta("Crew").get_field("trade").options or "").split("\n")
	match = next((o for o in options if o and o.lower() == (text or "").strip().lower()), None)
	return match or guess(TRADE_WORDS, text) or (text or _("Unassigned"))


# ---------------------------------------------------------------- productivity

def planned_rate(task, trade):
	"""(man-hours a unit, where it came from) for `task` worked by `trade`."""
	day = standard_hours() or 8
	sheet = estimate_for(task.boq, task.boq_item) if task.boq_item else None
	if sheet:
		rows = frappe.get_all("Estimate Resource", filters={"parent": sheet, "parenttype": "Estimate Sheet", "resource_type": "Labour",
		                                                    "output_per_day": [">", 0]}, fields=["description", "output_per_day"])
		row = next((r for r in rows if guess(TRADE_WORDS, r.description) == trade), rows[0] if rows else None)
		if row:
			heads = re.search(r"\((\d+)\)", row.description or "")
			gang = int(heads.group(1)) if heads else crew_headcount(task, trade) or 1
			return gang * day / flt(row.output_per_day), _("Estimate {0}").format(sheet)
	crew = task_crew(task, trade)
	if crew and flt(crew.standard_output) and crew.headcount:
		return crew.headcount * day / flt(crew.standard_output), _("Crew {0}").format(crew.crew_name)
	return None, _("No planned output")


def task_crew(task, trade):
	name = frappe.db.get_value("Task Resource", {"parent": task.name, "parenttype": "Task", "resource_type": "Labour", "crew": ["is", "set"],
	                                             "trade": trade}, "crew") or \
	       frappe.db.get_value("Task Resource", {"parent": task.name, "parenttype": "Task", "resource_type": "Labour", "crew": ["is", "set"]}, "crew")
	return frappe.db.get_value("Crew", name, ["crew_name", "headcount", "standard_output"], as_dict=True) if name else None


def crew_headcount(task, trade):
	crew = task_crew(task, trade)
	return crew.headcount if crew else None


def productivity(company=None, project=None, from_date=None, to_date=None, trade=None, wbs=None) -> list[dict]:
	values = {"company": company, "project": project, "from": from_date, "to": to_date}
	where = ["t.is_template = 0"]
	if company:
		where.append("t.company = %(company)s")
	if project:
		where.append("t.project = %(project)s")
	logged = defaultdict(lambda: {"site": 0.0, "typed": 0.0, "measured": False})  # (task, week)
	for r in frappe.db.sql(f"""select l.parent task, l.date, l.qty_done, l.source from `tabTask Progress Log` l join `tabTask` t on t.name = l.parent
		where l.parenttype = 'Task' and {' and '.join(where)}""" + (" and l.date >= %(from)s" if from_date else "") +
		(" and l.date <= %(to)s" if to_date else ""), values, as_dict=True):
		cell = logged[(r.task, monday(r.date))]
		if r.source == "Daily Site Report":
			cell["site"] += flt(r.qty_done)
			cell["measured"] = True
		else:
			cell["typed"] += flt(r.qty_done)
	qty = {k: (c["site"] if c["measured"] else c["typed"]) for k, c in logged.items()}
	crews = crews_of_employees()
	hours = defaultdict(float)  # (task, week, trade) -> hours
	sheet_rows = frappe.db.sql(f"""select d.task, date(d.from_time) day, ts.employee, sum(d.hours) hours
		from `tabTimesheet Detail` d join `tabTimesheet` ts on ts.name = d.parent join `tabTask` t on t.name = d.task
		where ts.docstatus = 1 and {' and '.join(where)}""" + (" and date(d.from_time) >= %(from)s" if from_date else "") +
		(" and date(d.from_time) <= %(to)s" if to_date else "") + " group by d.task, date(d.from_time), ts.employee", values, as_dict=True)
	on_tasks = crews_on_tasks({r.task for r in sheet_rows})
	for r in sheet_rows:
		mine = crews.get(r.employee) or []
		on_task = on_tasks.get(r.task, set())
		pick = next((c for c in mine if c[0] in on_task), mine[0] if mine else None)
		hours[(r.task, monday(r.day), pick[1] if pick else _("Unassigned"))] += flt(r.hours)
	tasks = {t.name: t for t in frappe.get_all("Task", filters={"name": ["in", list({k[0] for k in qty} | {k[0] for k in hours}) or [""]]},
	                                            fields=["name", "subject", "wbs", "uom", "boq", "boq_item", "project"])}
	rates = {}
	groups = {}
	keys = {(task, week, tr) for (task, week, tr) in hours} | {(task, week, None) for (task, week) in qty
	                                                         if not any(k[0] == task and k[1] == week for k in hours)}
	for task, week, tr in keys:
		t = tasks[task]
		if tr is None:  # progress with no hours booked: the task's planned trade, if any
			tr = frappe.db.get_value("Task Resource", {"parent": task, "parenttype": "Task", "resource_type": "Labour"}, "trade") or _("No hours booked")
		if (trade and tr != trade) or (wbs and t.wbs != wbs):
			continue
		if (task, tr) not in rates:
			rates[(task, tr)] = planned_rate(t, tr)
		rate, source = rates[(task, tr)]
		q, h = qty.get((task, week), 0.0), hours.get((task, week, tr), 0.0)
		g = groups.setdefault((week, tr, t.wbs, t.uom), {"week": week, "trade": tr, "wbs": t.wbs, "uom": t.uom, "project": t.project,
		                                                 "qty": 0.0, "hours": 0.0, "planned_hours": 0.0, "unplanned": 0, "tasks": set(), "sources": set()})
		g["qty"] += q
		g["hours"] += h
		g["tasks"].add(t.subject or task)
		if rate:
			g["planned_hours"] += q * rate
			g["sources"].add(source)
		elif q:
			g["unplanned"] = 1
	out = []
	for g in groups.values():
		g["output_per_hour"] = g["qty"] / g["hours"] if g["hours"] else None
		g["factor"] = g["planned_hours"] / g["hours"] if g["hours"] and g["planned_hours"] else None
		g["flag"] = 1 if g["factor"] is not None and g["factor"] < FLAG_BELOW else 0
		g["tasks"] = ", ".join(sorted(g["tasks"]))
		g["source"] = ", ".join(sorted(g["sources"])) or _("No planned output")
		del g["sources"]
		out.append(g)
	return sorted(out, key=lambda g: (g["week"], g["trade"], g["wbs"] or ""))


# ---------------------------------------------------------------- headcount

def headcount(company=None, project=None, from_date=None, to_date=None, trade=None) -> dict:
	"""{(week, trade): {"planned": peak, "actual": peak, "own": peak, "subcontract": peak}}."""
	from a3_constructa.overrides.task_resources import resource_loading

	planned_day = defaultdict(float)
	for r in resource_loading(project=project, from_date=from_date, to_date=to_date, company=company, resource_type="Labour", include_done=True):
		planned_day[(r["date"], r["group"])] += flt(r["qty"])
	who = trades_of_employees()
	own_day = defaultdict(set)
	values = {"company": company, "project": project, "from": from_date, "to": to_date, "present": PRESENT}
	cond = "a.docstatus = 1 and a.status in %(present)s" + (" and a.company = %(company)s" if company else "") + \
	       (" and a.project = %(project)s" if project else " and ifnull(a.project, '') != ''") + \
	       (" and a.attendance_date >= %(from)s" if from_date else "") + (" and a.attendance_date <= %(to)s" if to_date else "")
	for r in frappe.db.sql(f"select a.employee, a.attendance_date from `tabAttendance` a where {cond}", values, as_dict=True):
		own_day[(getdate(r.attendance_date), who.get(r.employee) or _("Unassigned"))].add(r.employee)
	sub_day = defaultdict(float)
	cond = "d.docstatus = 1" + (" and d.company = %(company)s" if company else "") + (" and d.project = %(project)s" if project else "") + \
	       (" and d.report_date >= %(from)s" if from_date else "") + (" and d.report_date <= %(to)s" if to_date else "")
	for r in frappe.db.sql(f"""select d.report_date, s.trade, sum(s.headcount) heads from `tabDSR Subcontractor` s
		join `tabDaily Site Report` d on d.name = s.parent where {cond} group by d.report_date, s.trade""", values, as_dict=True):
		sub_day[(getdate(r.report_date), trade_name(r.trade))] += flt(r.heads)
	weeks = defaultdict(lambda: {"planned": 0.0, "actual": 0.0, "own": 0.0, "subcontract": 0.0})
	days = set(planned_day) | set(own_day) | set(sub_day)
	for day, tr in days:
		if trade and tr != trade:
			continue
		w = weeks[(monday(day), tr)]
		own, sub = len(own_day.get((day, tr), ())), sub_day.get((day, tr), 0.0)
		w["planned"] = max(w["planned"], planned_day.get((day, tr), 0.0))
		w["actual"] = max(w["actual"], own + sub)
		w["own"] = max(w["own"], own)
		w["subcontract"] = max(w["subcontract"], sub)
	return weeks
