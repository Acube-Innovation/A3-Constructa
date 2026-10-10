# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Schedule Revision - catalogue 6.4: the programme frozen as a baseline.

Revision 0 is the original programme; each later revision re-baselines it, for a
reason (and, when a variation changed the programme, its variation order).
Submitting copies every open task's planned dates into the task's baseline and
into the revision's snapshot; a task never baselined before (on revision 0, a
completed one too) is taken as well. Cancelling the revision puts back the
baseline each task had before it.

The draft shows the snapshot it would freeze, how far each task's end has moved
against its current baseline, and how far the project's planned finish moves.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

from a3_constructa.overrides.task_baseline import set_variance

DONE = ("Completed", "Cancelled")


class ScheduleRevision(Document):
	def validate(self):
		if self.docstatus == 0:
			draft = frappe.db.get_value("Schedule Revision", {"project": self.project, "docstatus": 0, "name": ["!=", self.name or ""]}, "name")
			if draft:
				frappe.throw(_("{0} already has draft revision {1}: finish or delete it first.").format(self.project, draft))
			self.revision_no = next_revision(self.project)
			self.take_snapshot()

	def take_snapshot(self):
		self.set("tasks", [])
		for t in snapshot_tasks(self.project):
			moved = (getdate(t.exp_end_date) - getdate(t.baseline_end)).days if t.baseline_end else None
			self.append("tasks", {"task": t.name, "subject": t.subject, "wbs": t.wbs, "start": t.exp_start_date, "end": t.exp_end_date,
			                      "duration": 0 if cint(t.is_milestone) else (getdate(t.exp_end_date) - getdate(t.exp_start_date)).days + 1,
			                      "moved_days": moved})
		self.task_count = len(self.tasks)
		self.planned_finish = max((getdate(r.end) for r in self.tasks), default=None)
		previous = frappe.db.sql("""select max(baseline_end) from `tabTask` where project = %s and status != 'Cancelled'""", self.project)[0][0]
		self.previous_finish = previous
		self.finish_change_days = (getdate(self.planned_finish) - getdate(previous)).days if previous and self.planned_finish else None

	def before_submit(self):
		self.revision_no = next_revision(self.project)
		self.take_snapshot()
		if not self.tasks:
			frappe.throw(_("{0} has no dated open tasks to baseline.").format(self.project))
		self.approved_by = frappe.session.user

	def on_submit(self):
		for row in self.tasks:
			task = frappe.get_doc("Task", row.task)
			task.db_set({"baseline_start": row.start, "baseline_end": row.end, "baseline_revision": self.revision_no}, update_modified=False)
			set_variance(task, save=True)

	def on_cancel(self):
		later = frappe.db.get_value("Schedule Revision", {"project": self.project, "docstatus": 1, "revision_no": [">", self.revision_no]}, "name")
		if later:
			frappe.throw(_("Cancel the later revision {0} first.").format(later))
		for row in self.tasks:
			prior = frappe.db.sql("""select r.revision_no, t.start, t.end from `tabSchedule Revision Task` t
				join `tabSchedule Revision` r on r.name = t.parent
				where t.task = %s and r.docstatus = 1 and r.name != %s order by r.revision_no desc limit 1""", (row.task, self.name), as_dict=True)
			values = {"baseline_start": prior[0].start, "baseline_end": prior[0].end, "baseline_revision": prior[0].revision_no} if prior \
				else {"baseline_start": None, "baseline_end": None, "baseline_revision": 0}
			task = frappe.get_doc("Task", row.task)
			task.db_set(values, update_modified=False)
			set_variance(task, save=True)


def next_revision(project) -> int:
	last = frappe.db.sql("""select max(revision_no) from `tabSchedule Revision` where project = %s and docstatus = 1""", project)[0][0]
	return 0 if last is None else cint(last) + 1


def snapshot_tasks(project):
	"""Open dated tasks, and any never baselined (on revision 0, completed ones too)."""
	rows = frappe.get_all("Task", filters={"project": project, "is_template": 0, "status": ["!=", "Cancelled"],
	                                       "exp_start_date": ["is", "set"], "exp_end_date": ["is", "set"]},
	                      fields=["name", "subject", "wbs", "exp_start_date", "exp_end_date", "is_milestone", "status", "baseline_end"],
	                      order_by="exp_start_date asc, exp_end_date asc, name asc")
	return [t for t in rows if t.status not in DONE or not t.baseline_end]
