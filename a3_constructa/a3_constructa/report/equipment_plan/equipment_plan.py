# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Equipment Plan - catalogue 8.2: the machines the programme needs, week by week.

From the tasks' equipment (resource_loading, P-06B): per project, asset category
and week, the machine-days needed and the most machines needed on one day,
against the machines of that category on the project (owned or hired, not
scrapped or sold). Then:
- shortfall: the peak above what the project has;
- double bookings: a machine named on two tasks on the same days;
- Asset Movement needed: a named machine sitting on another project, or - for a
  shortfall - a machine of the category idle that week on another project (else
  hire).
Filters: company, project, category, from date, weeks.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, getdate, today

from a3_constructa.overrides.task_resources import resource_loading


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = plan(filters)
	return columns(filters), rows, None, chart(rows), summary(rows)


def monday(d):
	d = getdate(d)
	return getdate(add_days(d, -d.weekday()))


def machines() -> dict:
	"""{project: {category: [assets]}} for machines on a project."""
	out = defaultdict(lambda: defaultdict(list))
	for a in frappe.get_all("Asset", filters={"docstatus": ["<", 2], "status": ["not in", ["Scrapped", "Sold"]], "project": ["is", "set"]},
	                        fields=["name", "asset_name", "asset_category", "project"]):
		out[a.project][a.asset_category].append(a)
	return out


def named_rows(start, end):
	"""Task resource rows naming a machine, with the days it is needed."""
	rows = frappe.db.sql("""select r.asset, a.asset_name, a.project home, a.asset_category, t.name task, t.subject, t.project,
			t.exp_start_date, r.days
		from `tabTask Resource` r join `tabTask` t on t.name = r.parent and r.parenttype = 'Task'
		join `tabAsset` a on a.name = r.asset
		where r.resource_type = 'Equipment' and r.asset is not null and t.is_template = 0
			and t.status not in ('Cancelled', 'Completed', 'Template') and t.exp_start_date is not null""", as_dict=True)
	for r in rows:
		days = [getdate(add_days(r.exp_start_date, i)) for i in range(cint(r.days))]
		r.days_needed = [d for d in days if start <= d <= end]
	return [r for r in rows if r.days_needed]


def plan(filters) -> list[dict]:
	start = getdate(filters.get("from_date") or today())
	weeks = cint(filters.get("weeks") or 12)
	end = getdate(add_days(monday(start), weeks * 7 - 1))
	load = resource_loading(project=filters.get("project"), from_date=start, to_date=end, company=filters.get("company"),
	                        resource_type="Equipment")
	if filters.get("category"):
		load = [r for r in load if r["group"] == filters.category]
	have = machines()
	daily = defaultdict(float)  # (project, category, day) -> machines
	for r in load:
		daily[(r["project"], r["group"], getdate(r["date"]))] += flt(r["qty"])
	everywhere = defaultdict(float)  # (project, category, day) incl. other projects, for spare machines
	for r in resource_loading(from_date=start, to_date=end, resource_type="Equipment"):
		everywhere[(r["project"], r["group"], getdate(r["date"]))] += flt(r["qty"])
	named = named_rows(start, end)
	booked = defaultdict(list)  # (asset, day) -> rows
	for r in named:
		for d in r.days_needed:
			booked[(r.asset, d)].append(r)

	weeks_of = defaultdict(lambda: {"days": [], "machine_days": 0.0, "peak": 0.0})
	for (project, category, day), qty in daily.items():
		w = weeks_of[(project, category, monday(day))]
		w["days"].append(day); w["machine_days"] += qty; w["peak"] = max(w["peak"], qty)
	out = []
	for (project, category, week), w in sorted(weeks_of.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
		on_site = have[project].get(category, [])
		short = max(w["peak"] - len(on_site), 0)
		week_end = getdate(add_days(week, 6))
		doubles, moves = [], []
		for r in named:
			if r.project != project or r.asset_category != category:
				continue
			days = [d for d in r.days_needed if week <= d <= week_end]
			if not days:
				continue
			others = {o.task for d in days for o in booked[(r.asset, d)] if o.task != r.task}
			if others:
				clash = [d for d in days if len(booked[(r.asset, d)]) > 1]
				doubles.append(_("{0} also on {1} ({2})").format(
					r.asset_name, ", ".join(frappe.db.get_value("Task", o, "subject") for o in sorted(others)), span(clash)))
			if r.home != project:
				moves.append(_("Move {0} from {1} by {2}").format(r.asset_name, project_name(r.home) or _("the yard"), formatdate(min(days), "d MMM")))
		if short:
			spare = spares(project, category, w["days"], have, everywhere)
			for a in spare[: int(short)]:
				moves.append(_("Move {0} from {1} (idle that week)").format(a.asset_name, project_name(a.project)))
			if len(spare) < short:
				moves.append(_("Hire {0} more").format(int(short - len(spare))))
		out.append({"project": project, "category": category, "week": week, "machine_days": flt(w["machine_days"], 1),
		            "peak": w["peak"], "on_project": len(on_site), "shortfall": short,
		            "double_bookings": "; ".join(dict.fromkeys(doubles)), "movement": "; ".join(dict.fromkeys(moves)),
		            "machines": ", ".join(a.asset_name for a in on_site)})
	return out


def span(days):
	first, last = min(days), max(days)
	return formatdate(first, "d MMM") if first == last else f"{formatdate(first, 'd MMM')} – {formatdate(last, 'd MMM')}"


def project_name(project):
	return frappe.db.get_value("Project", project, "project_name") if project else None


def spares(project, category, days, have, everywhere):
	"""Machines of the category on other projects that their own project doesn't need on those days."""
	out = []
	for other, cats in have.items():
		if other == project:
			continue
		pool = cats.get(category, [])
		need = max((everywhere[(other, category, d)] for d in days), default=0)
		out += pool[int(need):]
	return out


def columns(filters):
	cols = [] if filters.get("project") else [{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100}]
	return cols + [
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Link", "options": "Asset Category", "width": 130},
		{"fieldname": "week", "label": _("Week of"), "fieldtype": "Date", "width": 100},
		{"fieldname": "machine_days", "label": _("Machine-days"), "fieldtype": "Float", "precision": 1, "width": 110},
		{"fieldname": "peak", "label": _("Peak / day"), "fieldtype": "Float", "precision": 0, "width": 90},
		{"fieldname": "on_project", "label": _("On Project"), "fieldtype": "Int", "width": 90},
		{"fieldname": "shortfall", "label": _("Shortfall"), "fieldtype": "Float", "precision": 0, "width": 85},
		{"fieldname": "double_bookings", "label": _("Double Bookings"), "fieldtype": "Data", "width": 260},
		{"fieldname": "movement", "label": _("Asset Movement Needed"), "fieldtype": "Data", "width": 300},
		{"fieldname": "machines", "label": _("Machines on the Project"), "fieldtype": "Data", "width": 220},
	]


def chart(rows):
	if not rows:
		return None
	weeks = sorted({r["week"] for r in rows})
	cats = sorted({r["category"] for r in rows})
	return {"data": {"labels": [formatdate(w, "d MMM") for w in weeks],
	                 "datasets": [{"name": c, "values": [sum(r["machine_days"] for r in rows if r["week"] == w and r["category"] == c) for w in weeks]}
	                              for c in cats]},
	        "type": "bar", "barOptions": {"stacked": 1}, "colors": ["#1c7ed6", "#f08c00", "#2f9e44", "#ae3ec9"]}


def summary(rows):
	short = [r for r in rows if r["shortfall"]]
	doubles = [r for r in rows if r["double_bookings"]]
	moves = [r for r in rows if r["movement"]]
	return [
		{"label": _("Machine-days needed"), "value": flt(sum(r["machine_days"] for r in rows), 1), "datatype": "Float"},
		{"label": _("Weeks short of machines"), "value": len(short), "datatype": "Int", "indicator": "Red" if short else "Green"},
		{"label": _("Double bookings"), "value": len(doubles), "datatype": "Int", "indicator": "Red" if doubles else "Green"},
		{"label": _("Movements needed"), "value": len(moves), "datatype": "Int", "indicator": "Orange" if moves else "Green"},
	]
