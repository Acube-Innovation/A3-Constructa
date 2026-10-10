# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Three-Week Look-Ahead - catalogue 6.5.

The tasks starting or running in the next 21 days (an unfinished task whose
dates have passed is still running), each checked against what it needs before
work can start:
- Material: its Task Resource materials (for work under way, the share not yet
  done) against stock in the project's stores (Warehouse.project) plus open
  purchase order quantity for the project due by the day it is needed. Tasks
  draw on the same stock in the order they need it.
- Crew: one is assigned (on the task or a labour line), and it is not on another
  open task over the same days in the next three weeks.
- Equipment: on each day a task's machines are needed, the project's tasks need
  no more machines of the category than there are on the project.
- Permits and drawings: ticked on the task.
- Predecessors: finish-to-start links finished, start-to-start links started
  (finish-to-finish and start-to-finish links don't hold up a start).
A task with every constraint clear is Ready.

"Commit week" sets committed_week (that Monday) on the Ready tasks starting next
week. The report shows last week's commitments against those kept - started
(or finished) by the end of that week - as the Percent Plan Complete (PPC).
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, getdate, today

from a3_constructa.overrides.task_resources import resource_loading

WINDOW = 21
OPEN = ("Completed", "Cancelled", "Template")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = look_ahead(filters)
	ppc = last_week(filters)
	return columns(filters), rows, message(ppc), None, summary(rows, ppc)


# ---------------------------------------------------------------- weeks

def monday(d):
	d = getdate(d)
	return add_days(d, -d.weekday())


def weeks(as_of=None):
	this = getdate(monday(as_of or today()))
	return {"last": getdate(add_days(this, -7)), "this": this, "next": getdate(add_days(this, 7))}


# ---------------------------------------------------------------- tasks

def task_filters(filters):
	conditions = ["t.is_template = 0", "t.is_group = 0", "t.is_milestone = 0"]
	values = {}
	if filters.get("project"):
		conditions.append("t.project = %(project)s"); values["project"] = filters.project
	if filters.get("wbs"):
		lft, rgt = frappe.db.get_value("WBS", filters.wbs, ["lft", "rgt"]) or (0, 0)
		conditions.append("t.wbs in (select name from `tabWBS` where lft >= %(lft)s and rgt <= %(rgt)s)")
		values.update(lft=lft, rgt=rgt)
	if filters.get("crew"):
		conditions.append("""(t.crew = %(crew)s or exists (select 1 from `tabTask Resource` r
			where r.parent = t.name and r.parenttype = 'Task' and r.crew = %(crew)s))""")
		values["crew"] = filters.crew
	return conditions, values


def span(t, as_of):
	"""The days an unfinished task occupies: its planned dates, to its forecast finish
	if that is later; work past its dates is still going on today."""
	start, end = getdate(t.exp_start_date), getdate(t.exp_end_date or t.exp_start_date)
	if t.get("forecast_end") and getdate(t.forecast_end) > end:
		end = getdate(t.forecast_end)
	return start, max(end, as_of) if start <= as_of else end


def crews_of(t, labour):
	return {c for c in [t.crew, *labour.get(t.name, [])] if c}


def look_ahead(filters) -> list[dict]:
	as_of = getdate(filters.get("as_of") or today())
	until = getdate(add_days(as_of, WINDOW - 1))
	conditions, values = task_filters(filters)
	values.update(until=until)
	tasks = frappe.db.sql(f"""select t.name, t.subject, t.project, t.wbs, t.crew, t.status, t.progress, t.exp_start_date, t.exp_end_date,
			t.forecast_end, t.permit_ready, t.drawings_ready, t.committed_week, t.act_start_date
		from `tabTask` t
		where {' and '.join(conditions)} and t.status not in {OPEN} and t.exp_start_date is not null and t.exp_start_date <= %(until)s
		order by t.exp_start_date, t.name""", values, as_dict=True)
	if not tasks:
		return []
	names = [t.name for t in tasks]
	labour = defaultdict(list)
	for r in frappe.get_all("Task Resource", filters={"parenttype": "Task", "resource_type": "Labour", "crew": ["is", "set"]},
	                        fields=["parent", "crew"]):
		labour[r.parent].append(r.crew)
	material = material_check(tasks, as_of)
	crew = crew_check(tasks, labour, as_of, until)
	equipment = equipment_check(tasks, as_of)
	preds = predecessor_check(names)
	out = []
	for t in tasks:
		start, end = span(t, as_of)
		checks = {
			"material": material.get(t.name),
			"crew_check": crew[t.name],
			"equipment": equipment.get(t.name),
			"permit": None if cint(t.permit_ready) else _("Not ready"),
			"drawings": None if cint(t.drawings_ready) else _("Not ready"),
			"predecessors": preds.get(t.name),
		}
		blockers = [k for k, v in checks.items() if is_blocked(v)]
		crew_id = t.crew or next(iter(labour.get(t.name, [])), None)
		row = {"task": t.name, "subject": t.subject, "project": t.project, "wbs": t.wbs, "crew": crew_id,
		       "crew_name": frappe.db.get_value("Crew", crew_id, "crew_name") if crew_id else None,
		       "start": start, "finish": end, "progress": flt(t.progress),
		       "state": _("Running") if start <= as_of else _("Starting"),
		       "ready": _("Ready") if not blockers else _("Not ready"), "blockers": len(blockers),
		       "committed_week": t.committed_week}
		for k, v in checks.items():
			row[k] = text(v)
		out.append(row)
	return out


def is_blocked(v):
	return bool(v) and not (isinstance(v, dict) and not v.get("blocked"))


def num(x) -> str:
	return f"{flt(x, 3):,.3f}".rstrip("0").rstrip(".")


def text(v):
	if v is None:
		return _("OK")
	if isinstance(v, dict):
		return v["text"]
	return v


# ---------------------------------------------------------------- material

def project_stores(project) -> list[str]:
	return frappe.get_all("Warehouse", filters={"project": project, "is_group": 0, "disabled": 0}, pluck="name")


def material_check(tasks, as_of) -> dict:
	"""Per task: None when its materials are covered, a dict {text, blocked} otherwise
	(or {text: "—"} when it needs none)."""
	by_name = {t.name: t for t in tasks}
	lines = frappe.get_all("Task Resource", filters={"parenttype": "Task", "parent": ["in", list(by_name)], "resource_type": "Material"},
	                       fields=["parent", "item_code", "description", "total_qty", "uom", "need_by_date"], order_by="idx")
	out = {name: {"text": "—", "blocked": False} for name in by_name}
	demands = defaultdict(list)  # (project, item) -> [(need date, qty, task)]
	unchecked = defaultdict(list)
	for r in lines:
		t = by_name[r.parent]
		share = 1 - min(flt(t.progress), 100) / 100
		qty = flt(flt(r.total_qty) * share, 3)
		if not r.item_code:
			unchecked[t.name].append(r.description or _("a material"))
			continue
		if qty <= 0:
			continue
		need = max(getdate(r.need_by_date or t.exp_start_date), as_of)
		demands[(t.project, r.item_code)].append((need, qty, t.name, r.uom))
		out[t.name] = None
	shorts = defaultdict(list)
	for (project, item), rows in demands.items():
		stock, orders = supply(project, item)
		used = 0.0
		for need, qty, task, uom in sorted(rows, key=lambda x: (x[0], x[2])):
			available = stock + sum(q for due, q in orders if due <= need) - used
			got = min(qty, max(available, 0))
			used += got
			if qty - got > 0.0005:
				shorts[task].append(_("{0} ({1} {2})").format(frappe.db.get_value("Item", item, "item_name") or item,
				                                            num(qty - got), uom or ""))
	for task, items in shorts.items():
		out[task] = {"text": _("Short: {0}").format("; ".join(i.strip() for i in items)), "blocked": True}
	for task, items in unchecked.items():
		if out[task] is None or out[task].get("text") == "—":
			out[task] = {"text": _("Not checked: {0} has no item").format(", ".join(items)), "blocked": False}
	return out


def supply(project, item):
	"""Stock of the item in the project's stores, and open PO quantity for the project
	[(due date, stock qty)]."""
	stores = project_stores(project)
	stock = flt(frappe.db.sql("""select sum(actual_qty) from tabBin where item_code = %s and warehouse in %s""",
	                          (item, stores))[0][0]) if stores else 0.0
	orders = frappe.db.sql("""select i.schedule_date, (i.qty - i.received_qty) * i.conversion_factor
		from `tabPurchase Order Item` i join `tabPurchase Order` po on po.name = i.parent
		where po.docstatus = 1 and po.status not in ('Closed', 'On Hold', 'Completed') and i.item_code = %(item)s
			and i.qty > i.received_qty and (i.project = %(project)s or i.warehouse in %(stores)s)""",
	                       {"item": item, "project": project, "stores": stores or [""]})
	return max(stock, 0.0), [(getdate(due), flt(q)) for due, q in orders]


# ---------------------------------------------------------------- crew

def crew_check(tasks, labour, as_of, until) -> dict:
	"""Per task: None when a crew is assigned and free, else the reason. Clashes are
	looked for against every open task (any project) over the next three weeks."""
	others = frappe.db.sql(f"""select t.name, t.subject, t.project, t.crew, t.exp_start_date, t.exp_end_date, t.forecast_end
		from `tabTask` t
		where t.is_template = 0 and t.is_group = 0 and t.is_milestone = 0 and t.status not in {OPEN}
			and t.exp_start_date is not null and t.exp_start_date <= %(until)s
			and (t.crew is not null or exists (select 1 from `tabTask Resource` r where r.parent = t.name and r.parenttype = 'Task'
				and r.resource_type = 'Labour' and r.crew is not null))""", {"until": until}, as_dict=True)
	booked = defaultdict(list)  # crew -> [(start, end, task)]
	for o in others:
		s, e = span(o, as_of)
		s, e = max(s, as_of), min(e, until)
		if s > e:
			continue
		for c in crews_of(o, labour):
			booked[c].append((s, e, o))
	out = {}
	for t in tasks:
		crews = crews_of(t, labour)
		if not crews:
			out[t.name] = {"text": _("Not assigned"), "blocked": True}
			continue
		s, e = span(t, as_of)
		s, e = max(s, as_of), min(e, until)
		clashes = []
		for c in sorted(crews):
			for os_, oe, o in booked[c]:
				if o.name != t.name and os_ <= e and oe >= s:
					clashes.append(_("also on {0} ({1} – {2})").format(o.subject, formatdate(max(s, os_), "d MMM"), formatdate(min(e, oe), "d MMM")))
		out[t.name] = {"text": _("Double-booked: {0}").format("; ".join(clashes)), "blocked": True} if clashes else None
	return out


# ---------------------------------------------------------------- equipment

def machines_on(project) -> dict:
	"""Machines on the project by asset category (owned or hired, not scrapped or sold)."""
	rows = frappe.db.sql("""select asset_category, count(*) from tabAsset where project = %s and docstatus < 2
		and status not in ('Scrapped', 'Sold') group by asset_category""", project)
	return {c: cint(n) for c, n in rows}


def equipment_check(tasks, as_of) -> dict:
	out = {}
	for project in {t.project for t in tasks if t.project}:
		have = machines_on(project)
		need = defaultdict(float)  # (category, day) -> machines
		mine = defaultdict(list)   # task -> [(category, day)]
		for r in resource_loading(project=project, from_date=as_of, resource_type="Equipment"):
			need[(r["group"], r["date"])] += flt(r["qty"])
			mine[r["task"]].append((r["group"], r["date"]))
		for t in tasks:
			if t.project != project:
				continue
			if not mine.get(t.name):
				has_rows = frappe.db.exists("Task Resource", {"parent": t.name, "parenttype": "Task", "resource_type": "Equipment"})
				out[t.name] = {"text": "—" if not has_rows else _("OK"), "blocked": False}
				continue
			short = defaultdict(list)
			for category, d in mine[t.name]:
				gap = need[(category, d)] - have.get(category, 0)
				if gap > 0:
					short[category].append((d, gap))
			if not short:
				out[t.name] = None
				continue
			parts = []
			for category, days in short.items():
				first, last = min(d for d, _g in days), max(d for d, _g in days)
				parts.append(_("{0} more {1} ({2} – {3}; {4} on the project)").format(
					num(max(g for _d, g in days)), category, formatdate(first, "d MMM"),
					formatdate(last, "d MMM"), have.get(category, 0)))
			out[t.name] = {"text": _("Short: {0}").format("; ".join(parts)), "blocked": True}
	return out


# ---------------------------------------------------------------- predecessors

def predecessor_check(names) -> dict:
	links = frappe.db.sql("""select d.parent, d.task, d.dependency_type, p.subject, p.status, p.progress, p.act_start_date,
			exists (select 1 from `tabTask Progress Log` l where l.parent = p.name and l.parenttype = 'Task' and l.qty_done > 0) logged
		from `tabTask Depends On` d join `tabTask` p on p.name = d.task
		where d.parenttype = 'Task' and d.parent in %s""", [names], as_dict=True)
	waiting = defaultdict(list)
	for d in links:
		kind = d.dependency_type or "FS"
		done = d.status in ("Completed", "Cancelled")
		started = done or flt(d.progress) > 0 or bool(d.act_start_date) or cint(d.logged)
		if kind == "FS" and not done:
			waiting[d.parent].append(_("{0} to finish").format(d.subject))
		elif kind == "SS" and not started:
			waiting[d.parent].append(_("{0} to start").format(d.subject))
	return {n: {"text": _("Waiting: {0}").format("; ".join(w)), "blocked": True} for n, w in waiting.items()}


# ---------------------------------------------------------------- commitments

def kept(task, week_end) -> bool:
	"""Started (or finished) by the end of the committed week."""
	if task.status == "Completed" and (not task.completed_on or getdate(task.completed_on) <= week_end):
		return True
	if task.act_start_date and getdate(task.act_start_date) <= week_end:
		return True
	return bool(frappe.db.sql("""select 1 from `tabTask Progress Log` where parent = %s and parenttype = 'Task'
		and qty_done > 0 and date <= %s limit 1""", (task.name, week_end)))


def last_week(filters) -> dict:
	w = weeks(filters.get("as_of"))
	week_end = getdate(add_days(w["last"], 6))
	conditions, values = task_filters(filters)
	values["week"] = w["last"]
	tasks = frappe.db.sql(f"""select t.name, t.subject, t.status, t.completed_on, t.act_start_date from `tabTask` t
		where {' and '.join(conditions)} and t.committed_week = %(week)s and t.status != 'Cancelled' order by t.exp_start_date, t.name""",
	                      values, as_dict=True)
	done = [t for t in tasks if kept(t, week_end)]
	missed = [t for t in tasks if t not in done]
	return {"week": w["last"], "week_end": week_end, "committed": len(tasks), "kept": len(done),
	        "ppc": flt(len(done) / len(tasks) * 100, 1) if tasks else None, "missed": [t.subject for t in missed],
	        "missed_tasks": [t.name for t in missed]}


@frappe.whitelist()
def commit_week(filters=None) -> dict:
	"""Commit the Ready tasks starting next week: committed_week = next Monday."""
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	frappe.has_permission("Task", "write", throw=True)
	w = weeks(filters.get("as_of"))
	start, end = w["next"], getdate(add_days(w["next"], 6))
	made, already, not_ready = [], [], []
	for r in look_ahead(filters):
		if not (start <= getdate(r["start"]) <= end):
			continue
		if r["ready"] != _("Ready"):
			not_ready.append(r["subject"])
			continue
		if r["committed_week"] and getdate(r["committed_week"]) == start:
			already.append(r["subject"])
			continue
		task = frappe.get_doc("Task", r["task"])
		task.check_permission("write")
		task.db_set("committed_week", start)
		task.add_comment("Info", _("Committed for the week of {0} (Three-Week Look-Ahead).").format(formatdate(start, "d MMM yyyy")))
		made.append(r["subject"])
	return {"week": start, "committed": made, "already": already, "not_ready": not_ready}


# ---------------------------------------------------------------- output

def columns(filters):
	cols = [
		{"fieldname": "task", "label": _("Task"), "fieldtype": "Link", "options": "Task", "width": 120},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 230},
	]
	if not filters.get("project"):
		cols.append({"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100})
	cols += [
		{"fieldname": "start", "label": _("Start"), "fieldtype": "Date", "width": 100},
		{"fieldname": "finish", "label": _("Finish"), "fieldtype": "Date", "width": 100},
		{"fieldname": "ready", "label": _("Ready?"), "fieldtype": "Data", "width": 100},
		{"fieldname": "material", "label": _("Material"), "fieldtype": "Data", "width": 290},
		{"fieldname": "crew_name", "label": _("Crew"), "fieldtype": "Data", "width": 130},
		{"fieldname": "crew_check", "label": _("Crew Free"), "fieldtype": "Data", "width": 290},
		{"fieldname": "equipment", "label": _("Equipment"), "fieldtype": "Data", "width": 290},
		{"fieldname": "permit", "label": _("Permits"), "fieldtype": "Data", "width": 85},
		{"fieldname": "drawings", "label": _("Drawings"), "fieldtype": "Data", "width": 85},
		{"fieldname": "predecessors", "label": _("Predecessors"), "fieldtype": "Data", "width": 280},
		{"fieldname": "state", "label": _("State"), "fieldtype": "Data", "width": 80},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 110},
		{"fieldname": "crew", "label": _("Crew ID"), "fieldtype": "Link", "options": "Crew", "width": 95},
		{"fieldname": "committed_week", "label": _("Committed Week"), "fieldtype": "Date", "width": 120},
	]
	return cols


def message(ppc):
	if not ppc["committed"]:
		return _("Last week ({0} – {1}): nothing was committed.").format(formatdate(ppc["week"], "d MMM"), formatdate(ppc["week_end"], "d MMM"))
	text = _("Last week ({0} – {1}): {2} of {3} commitments kept, PPC {4}%.").format(
		formatdate(ppc["week"], "d MMM"), formatdate(ppc["week_end"], "d MMM"), ppc["kept"], ppc["committed"], num(ppc["ppc"]))
	if ppc["missed"]:
		text += " " + _("Not started: {0}.").format(", ".join(frappe.bold(m) for m in ppc["missed"]))
	return text


def summary(rows, ppc):
	ready = sum(1 for r in rows if r["ready"] == _("Ready"))
	out = [{"label": _("Tasks in the next 21 days"), "value": len(rows), "datatype": "Int"},
	       {"label": _("Ready"), "value": ready, "datatype": "Int", "indicator": "Green"},
	       {"label": _("Not ready"), "value": len(rows) - ready, "datatype": "Int", "indicator": "Red" if len(rows) - ready else "Green"}]
	if ppc["committed"]:
		out.append({"label": _("Last week: committed / kept"), "value": f"{ppc['committed']} / {ppc['kept']}", "datatype": "Data"})
		out.append({"label": _("PPC last week"), "value": f"{ppc['ppc']:g}%", "datatype": "Data",
		            "indicator": "Green" if ppc["ppc"] >= 80 else ("Orange" if ppc["ppc"] >= 60 else "Red")})
	return out
