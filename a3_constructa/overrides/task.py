# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Tasks on the WBS - catalogue 6.1 and 6.2.

A task carries its WBS node (required when its project has a WBS, and from that
project), cost code, planned quantity, foreman; sub-tasks' weights under one
parent may not pass 100%.

Links between tasks have a type (FS, SS, FF, SF) and a lag in days. When a task
moves, its successors that the move would now break are pushed later, keeping
their duration, and theirs in turn; completed and cancelled tasks stay put. A
successor is never pulled earlier: the room that opens is float.

After every change the project's network is passed forwards and backwards: each
task's total float is how many days it can slip without moving the project's
finish, and a task with no float is critical. Dates are calendar days; a task's
planned start counts as "start no earlier than"; a milestone takes no time.
"""

from datetime import timedelta

import frappe
from erpnext.projects.doctype.task.task import Task
from frappe import _
from frappe.utils import cint, flt, format_date, getdate

DONE = ("Completed", "Cancelled")


class ConstructaTask(Task):
	def reschedule_dependent_tasks(self):
		"""Replaces ERPNext's, which knows only finish-to-start without lag."""
		push_successors(self)


# ---------------------------------------------------------------- validate

def validate(doc, method=None):
	check_wbs(doc)
	check_weights(doc)
	for row in doc.depends_on:
		row.dependency_type = row.dependency_type or "FS"
		row.lag_days = cint(row.lag_days)
		if row.task == doc.name:
			frappe.throw(_("Row {0}: a task cannot depend on itself.").format(row.idx))


def check_wbs(doc):
	if not doc.project or doc.is_template:
		return
	if doc.wbs:
		project = frappe.db.get_value("WBS", doc.wbs, "project")
		if project != doc.project:
			frappe.throw(_("WBS {0} belongs to {1}, not to this task's project {2}.").format(doc.wbs, project or _("no project"), doc.project),
			             title=_("WBS"))
	elif frappe.db.exists("WBS", {"project": doc.project}):
		frappe.throw(_("Project {0} has a WBS: set the task's WBS node.").format(doc.project), title=_("WBS"))


def check_weights(doc):
	if not doc.parent_task or not flt(doc.task_weight):
		return
	siblings = flt(frappe.db.sql("""select sum(task_weight) from `tabTask` where parent_task = %s and name != %s and status != 'Cancelled'""",
	                             (doc.parent_task, doc.name or ""))[0][0])
	total = siblings + flt(doc.task_weight)
	if total > 100 + 1e-9:
		frappe.throw(_("Sub-task weights under {0} would add up to {1}%: they must total 100%.").format(doc.parent_task, flt(total, 2)),
		             title=_("Weights"))
	if total < 100 - 1e-9:
		frappe.msgprint(_("Sub-task weights under {0} add up to {1}% so far; they must reach 100%.").format(doc.parent_task, flt(total, 2)),
		                indicator="orange", alert=True)


# ---------------------------------------------------------------- rescheduling

def duration(task) -> int:
	"""Days from start to end; 0 for a milestone or a one-day task."""
	return (getdate(task.exp_end_date) - getdate(task.exp_start_date)).days


def earliest_start(pred, succ_duration, kind, lag):
	"""The earliest start a link allows the successor, from its predecessor's dates."""
	lag = timedelta(days=cint(lag))
	start, end = getdate(pred.exp_start_date), getdate(pred.exp_end_date)
	after_end = end + timedelta(days=0 if cint(pred.is_milestone) else 1)
	span = timedelta(days=succ_duration)
	return {"FS": after_end + lag, "SS": start + lag, "FF": end + lag - span, "SF": start + lag - span}.get(kind or "FS", after_end + lag)


def push_successors(task):
	# A bulk edit (an import, the demo loader) sets its links and dates as a whole.
	if frappe.flags.a3_no_reschedule or not task.exp_start_date or not task.exp_end_date:
		return
	rows = frappe.get_all("Task Depends On", filters={"task": task.name, "parenttype": "Task"}, fields=["parent", "dependency_type", "lag_days"])
	frappe.flags.a3_task_cascade = cint(frappe.flags.a3_task_cascade) + 1
	try:
		for row in rows:
			succ = frappe.get_doc("Task", row.parent)
			if succ.status in DONE or not succ.exp_start_date or not succ.exp_end_date:
				continue
			need = earliest_start(task, duration(succ), row.dependency_type, row.lag_days)
			if getdate(succ.exp_start_date) >= need:
				continue
			shift = need - getdate(succ.exp_start_date)
			succ.exp_start_date = need
			succ.exp_end_date = getdate(succ.exp_end_date) + shift
			stretch_parent(succ)
			succ.flags.ignore_recursion_check = True
			succ.flags.ignore_permissions = True
			try:
				succ.save()
			except frappe.exceptions.InvalidDates as e:
				frappe.throw(_("Moving {0} pushes {1} to {2}: {3}").format(frappe.bold(task.subject), frappe.bold(succ.subject),
				                                                          format_date(succ.exp_start_date), frappe.utils.strip_html(str(e))),
				             frappe.exceptions.InvalidDates, title=_("Reschedule"))
	finally:
		frappe.flags.a3_task_cascade = cint(frappe.flags.a3_task_cascade) - 1


def stretch_parent(task):
	"""A pushed sub-task may end after its parent: the parent ends with it."""
	if task.parent_task:
		end = frappe.db.get_value("Task", task.parent_task, "exp_end_date")
		if end and getdate(end) < getdate(task.exp_end_date):
			frappe.db.set_value("Task", task.parent_task, "exp_end_date", task.exp_end_date)


# ---------------------------------------------------------------- critical path

def on_update(doc, method=None):
	if doc.project and not cint(frappe.flags.a3_task_cascade):
		critical_path(doc.project)


def after_delete(doc, method=None):
	if doc.project:
		critical_path(doc.project)


def critical_path(project) -> dict:
	"""Forward and backward pass over the project's dated tasks; stores each task's
	total float and whether it is critical. Group tasks summarise their children and
	are left out of the network."""
	tasks = {t.name: t for t in frappe.get_all("Task", filters={"project": project, "is_group": 0, "is_template": 0, "status": ["!=", "Cancelled"],
	                                                             "exp_start_date": ["is", "set"], "exp_end_date": ["is", "set"]},
	                                             fields=["name", "exp_start_date", "exp_end_date", "is_milestone", "status",
	                                                     "total_float_days", "is_critical"])}
	if not tasks:
		return {}
	links = [r for r in frappe.get_all("Task Depends On", filters={"parent": ["in", list(tasks)], "parenttype": "Task"},
	                                   fields=["parent", "task", "dependency_type", "lag_days"]) if r.task in tasks]
	preds, succs = {n: [] for n in tasks}, {n: [] for n in tasks}
	for r in links:
		preds[r.parent].append(r)
		succs[r.task].append(r)
	order = topological(tasks, preds)
	day = lambda d: getdate(d).toordinal()
	dur = {n: day(t.exp_end_date) - day(t.exp_start_date) for n, t in tasks.items()}
	gap = {n: 0 if cint(t.is_milestone) else 1 for n, t in tasks.items()}
	es, ef = {}, {}
	for n in order:
		start = day(tasks[n].exp_start_date)
		for r in preds[n]:
			p, lag = r.task, cint(r.lag_days)
			start = max(start, {"FS": ef[p] + gap[p] + lag, "SS": es[p] + lag, "FF": ef[p] + lag - dur[n], "SF": es[p] + lag - dur[n]}
			            .get(r.dependency_type or "FS", ef[p] + gap[p] + lag))
		es[n], ef[n] = start, start + dur[n]
	finish = max(ef.values())
	lf = {}
	for n in reversed(order):
		latest = finish
		for r in succs[n]:
			s, lag = r.parent, cint(r.lag_days)
			ls_s = lf[s] - dur[s]
			latest = min(latest, {"FS": ls_s - gap[n] - lag, "SS": ls_s - lag + dur[n], "FF": lf[s] - lag, "SF": lf[s] - lag + dur[n]}
			             .get(r.dependency_type or "FS", ls_s - gap[n] - lag))
		lf[n] = latest
	result = {}
	for n, t in tasks.items():
		total_float = lf[n] - ef[n]
		critical = int(total_float <= 0 and t.status not in DONE)
		result[n] = {"float": total_float, "critical": critical, "early_start": es[n], "late_finish": lf[n]}
		if t.total_float_days != total_float or t.is_critical != critical:
			frappe.db.set_value("Task", n, {"total_float_days": total_float, "is_critical": critical}, update_modified=False)
	return result


def topological(tasks, preds):
	"""Predecessors before successors; a loop in the links is refused."""
	order, state = [], {}

	def visit(n, path):
		if state.get(n) == 2:
			return
		if state.get(n) == 1:
			frappe.throw(_("The task links go round in a circle: {0}.").format(" → ".join(path + [n])), title=_("Circular links"))
		state[n] = 1
		for r in preds[n]:
			visit(r.task, path + [n])
		state[n] = 2
		order.append(n)

	for n in sorted(tasks):
		visit(n, [])
	return order


@frappe.whitelist()
def recalculate(project: str) -> int:
	frappe.has_permission("Project", "read", doc=project, throw=True)
	return sum(r["critical"] for r in critical_path(project).values())


# ---------------------------------------------------------------- award milestones

@frappe.whitelist()
def create_schedule_milestones(award: str) -> list[str]:
	"""A zero-duration milestone task for each of the award's milestones, on its
	component's WBS (else the project's top node); already-made ones are updated."""
	from a3_constructa.api.milestone_billing import component_wbs

	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("read")
	frappe.has_permission("Task", "create", throw=True)
	if not a.project:
		frappe.throw(_("Hand {0} over to a project first.").format(a.name))
	made = []
	for row in a.milestones:
		if not row.planned_end:
			continue
		name = frappe.db.get_value("Task", {"award_milestone": row.name})
		t = frappe.get_doc("Task", name) if name else frappe.new_doc("Task")
		t.update({"subject": _("Milestone: {0}").format(row.milestone)[:140], "project": a.project, "is_milestone": 1,
		          "exp_start_date": row.planned_end, "exp_end_date": row.planned_end, "awarded_quotation": a.name, "award_milestone": row.name,
		          "wbs": t.wbs or component_wbs(a, row) or root_wbs(a.project)})
		if row.actual_end:
			t.update({"status": "Completed", "completed_on": min(getdate(row.actual_end), getdate()), "progress": 100})
		t.flags.ignore_permissions = True
		t.save()
		made.append(t.name)
	return made


def root_wbs(project):
	roots = frappe.get_all("WBS", filters={"project": project, "parent_wbs": ["is", "not set"]}, pluck="name")
	return roots[0] if len(roots) == 1 else None
