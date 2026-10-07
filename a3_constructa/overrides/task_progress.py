# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Progress by quantity and WBS roll-up - catalogue 6.6.

A task's progress is measured three ways:
- Quantity: the quantity done (its progress log added up) ÷ the planned quantity;
- Sub-tasks: a group task follows its sub-tasks, weighted by their task weight
  (equally when no weights are set);
- Manual: the % entered.

From the rate achieved so far - progress since the work started, over the days
it has taken up to the last measurement - the task forecasts its remaining
duration and its finish. Work not started keeps its planned dates.

A WBS node's progress is the budget-weighted average of the work under it: the
node's own tasks (weighted by duration among themselves) carry the budget held on
the node itself, and each child node its own budget (wbs_budget, from the budget
log and submitted allocations). Budget with no tasks under it counts as not
started, so % complete and earned value (% × budget) agree; where no part has a
budget, the measured parts are averaged. It is kept on the WBS and recalculated
whenever a task of the project changes.
"""

import math

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today

from a3_constructa.api.budget_allocation import wbs_budget

DONE = ("Completed",)


# ---------------------------------------------------------------- task

def validate(doc, method=None):
	doc.qty_done = flt(sum(flt(r.qty_done) for r in doc.get("progress_log") or []), 3)
	method_ = doc.get("progress_method") or "Manual"
	if method_ == "Quantity":
		if flt(doc.planned_qty):
			doc.progress = min(100.0, flt(doc.qty_done / flt(doc.planned_qty) * 100, 2))
		elif doc.progress_log:
			frappe.msgprint(_("Enter the planned quantity: progress by quantity is quantity done ÷ planned quantity."),
			                indicator="orange", alert=True)
	elif method_ == "Sub-tasks":
		if not cint(doc.is_group):
			frappe.throw(_("Only a group task can take its progress from sub-tasks."), title=_("Progress method"))
		if not doc.is_new():
			doc.progress = subtask_progress(doc.name)
	if doc.status in DONE:
		doc.progress = 100
	forecast(doc)


def subtask_progress(name) -> float:
	children = frappe.get_all("Task", filters={"parent_task": name, "status": ["!=", "Cancelled"]}, fields=["progress", "task_weight", "status"])
	if not children:
		return 0
	weights = [flt(c.task_weight) for c in children]
	if not sum(weights):
		weights = [1.0] * len(children)
	return flt(sum(w * (100 if c.status in DONE else flt(c.progress)) for w, c in zip(weights, children)) / sum(weights), 2)


def started_on(doc):
	"""The actual start, else the planned start (the first measurement comes after work began)."""
	dates = [getdate(r.date) for r in doc.get("progress_log") or [] if flt(r.qty_done)]
	if doc.get("act_start_date"):
		return getdate(doc.act_start_date)
	if not dates:
		return None
	return min(getdate(doc.exp_start_date), min(dates)) if doc.exp_start_date else min(dates)


def forecast(doc):
	"""Remaining duration and forecast finish from the rate achieved so far."""
	progress = flt(doc.progress)
	if not doc.exp_start_date or not doc.exp_end_date:
		doc.remaining_duration, doc.forecast_end = None, None
		return
	planned = 0 if cint(doc.is_milestone) else (getdate(doc.exp_end_date) - getdate(doc.exp_start_date)).days + 1
	logs = [getdate(r.date) for r in doc.get("progress_log") or []]
	as_of = max(logs) if logs else getdate(today())
	if progress >= 100 or doc.status in DONE:
		doc.remaining_duration = 0
		doc.forecast_end = doc.get("act_end_date") or doc.get("completed_on") or (max(logs) if logs else doc.exp_end_date)
		return
	start = started_on(doc) or (getdate(doc.exp_start_date) if progress else None)
	if not progress or not start:
		doc.remaining_duration = planned
		doc.forecast_end = doc.exp_end_date
		return
	elapsed = max((as_of - start).days + 1, 1)
	remaining = math.ceil((100 - progress) / (progress / elapsed))
	doc.remaining_duration = remaining
	doc.forecast_end = frappe.utils.add_days(as_of, remaining)


def on_update(doc, method=None):
	"""A sub-task's progress moves its group task; any change moves the WBS roll-up."""
	parent = doc.get("parent_task")
	seen = set()
	while parent and parent not in seen:
		seen.add(parent)
		p = frappe.get_doc("Task", parent)
		if p.get("progress_method") != "Sub-tasks":
			break
		p.progress = subtask_progress(p.name)
		forecast(p)
		p.db_set({"progress": p.progress, "remaining_duration": p.remaining_duration, "forecast_end": p.forecast_end}, update_modified=False)
		parent = p.parent_task
	if doc.project and not cint(frappe.flags.a3_task_cascade):
		update_wbs_progress(doc.project)


@frappe.whitelist()
def record_progress(task: str, date: str, qty_done: float, reference: str | None = None, remarks: str | None = None,
                    source: str = "Manual") -> float:
	"""Add a measurement to a task's progress log; returns the task's new progress."""
	t = frappe.get_doc("Task", task)
	t.check_permission("write")
	if flt(qty_done) <= 0:
		frappe.throw(_("Enter the quantity done."))
	t.append("progress_log", {"date": date, "qty_done": flt(qty_done), "source": source, "reference": reference, "remarks": remarks})
	t.progress_method = t.progress_method if t.progress_method != "Manual" else "Quantity"
	t.flags.ignore_permissions = True
	t.save()
	return t.progress


# ---------------------------------------------------------------- WBS

def planned_percent(task, as_of) -> float:
	"""Where the baseline (else the plan) says the task should be on `as_of`."""
	start, end = task.baseline_start or task.exp_start_date, task.baseline_end or task.exp_end_date
	if not start or not end:
		return 0
	start, end, as_of = getdate(start), getdate(end), getdate(as_of)
	if as_of < start:
		return 0
	if as_of >= end:
		return 100
	return flt(((as_of - start).days + 1) / ((end - start).days + 1) * 100, 2)


def wbs_progress(project, as_of=None) -> dict:
	"""Per WBS node: budget, % complete and % planned (on `as_of`), rolled up the tree."""
	as_of = getdate(as_of or today())
	nodes = {w.name: w for w in frappe.get_all("WBS", filters={"project": project},
	                                           fields=["name", "wbs_name", "parent_wbs", "lft", "rgt", "is_group"], order_by="lft")}
	if not nodes:
		return {}
	tasks = frappe.get_all("Task", filters={"project": project, "is_template": 0, "is_group": 0, "status": ["!=", "Cancelled"],
	                                        "is_milestone": 0, "wbs": ["is", "set"]},
	                       fields=["name", "wbs", "progress", "status", "exp_start_date", "exp_end_date", "baseline_start", "baseline_end"])
	own = {}
	for t in tasks:
		days = ((getdate(t.exp_end_date) - getdate(t.exp_start_date)).days + 1) if t.exp_start_date and t.exp_end_date else 1
		agg = own.setdefault(t.wbs, {"w": 0.0, "done": 0.0, "plan": 0.0})
		agg["w"] += days
		agg["done"] += days * (100 if t.status in DONE else flt(t.progress))
		agg["plan"] += days * planned_percent(t, as_of)
	children = {}
	for n in nodes.values():
		if n.parent_wbs in nodes:
			children.setdefault(n.parent_wbs, []).append(n.name)
	budget = {n: flt(wbs_budget(project, n)) for n in nodes}
	out = {}

	def visit(name):
		parts = []  # (budget, done %, planned %, measured)
		kids = children.get(name, [])
		for k in kids:
			visit(k)
			parts.append((budget[k], out[k]["percent"], out[k]["planned"], out[k]["measured"]))
		own_budget = max(budget[name] - sum(budget[k] for k in kids), 0)
		if name in own and own[name]["w"]:
			a = own[name]
			parts.append((own_budget, a["done"] / a["w"], a["plan"] / a["w"], True))
		elif own_budget:
			parts.append((own_budget, 0.0, 0.0, False))  # budget held here with no task yet: not started
		measured = any(m for *_, m in parts)
		total = sum(w for w, *_ in parts)
		if total:
			# Budget not yet measured (no tasks) counts as not started, so % and earned value agree.
			percent = sum(w * d for w, d, _, _ in parts) / total
			planned = sum(w * p for w, _, p, _ in parts) / total
		else:
			done = [(d, p) for _, d, p, m in parts if m]
			percent = sum(d for d, _ in done) / len(done) if done else 0
			planned = sum(p for _, p in done) / len(done) if done else 0
		out[name] = {"wbs_name": nodes[name].wbs_name, "parent": nodes[name].parent_wbs, "lft": nodes[name].lft, "budget": budget[name],
		             # A node with budget but no tasks yet shows as not started, as its parent counts it.
		             "measured": measured or bool(total) or budget[name] > 0, "percent": flt(percent, 2), "planned": flt(planned, 2)}

	for root in [n for n in nodes.values() if n.parent_wbs not in nodes]:
		visit(root.name)
	return out


def update_wbs_progress(project):
	for name, r in wbs_progress(project).items():
		if flt(frappe.db.get_value("WBS", name, "progress_percent")) != r["percent"]:
			frappe.db.set_value("WBS", name, "progress_percent", r["percent"], update_modified=False)
