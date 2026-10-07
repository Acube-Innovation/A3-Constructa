# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Quality inspections and NCRs on the WBS - catalogue 6.8.

ERPNext's Quality Inspection checks goods: it wants a reference document and an
item. A site inspection checks work instead: it carries a project, WBS and task,
an inspection point (Hold / Witness / Surveillance) and a request number, and
needs no item or reference (those stay mandatory for an inspection of goods).

- "Request inspection" on a task raises a draft inspection with the checklist of
  the task's type (Task Type.quality_inspection_template). Until a reading is
  entered it has no result.
- Submitting a rejected inspection raises a Non Conformance (status Open) linked
  to it, on the same project, WBS and task.
- A Non Conformance moves Open → Action Taken (with the corrective action) →
  Closed (closed_on set); reopening clears closed_on.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

READING_FIELDS = ["reading_value", *[f"reading_{i}" for i in range(1, 11)]]


# ---------------------------------------------------------------- inspection

def qi_validate(doc, method=None):
	if not doc.get("task"):
		# An inspection of goods: ERPNext's own requirements, made conditional on there being no task.
		missing = [doc.meta.get_label(f) for f in ("reference_type", "reference_name", "item_code") if not doc.get(f)]
		if missing:
			frappe.throw(_("An inspection of goods needs {0}; for work on site, choose the task.").format(", ".join(missing)),
			             title=_("Missing fields"))
		return
	project, wbs = frappe.db.get_value("Task", doc.task, ["project", "wbs"])
	if doc.project and doc.project != project:
		frappe.throw(_("Task {0} is on {1}, not {2}.").format(doc.task, project, doc.project))
	doc.project = project
	doc.wbs = doc.wbs or wbs
	doc.inspection_type = doc.inspection_type or "In Process"
	doc.company = doc.company or frappe.db.get_value("Project", project, "company")
	if not doc.request_no:
		doc.request_no = next_request_no(project)
	if not cint(doc.manual_inspection) and not any(
		(r.get(f) or "").strip() for r in doc.readings for f in READING_FIELDS
	):
		# Requested, not yet inspected: no result until a reading is entered.
		if doc.docstatus == 1:
			frappe.throw(_("Enter the readings: the inspection has no result yet."), title=_("Not inspected"))
		doc.status = None
		for r in doc.readings:
			if not cint(r.manual_inspection):
				r.status = None


def qi_before_submit(doc, method=None):
	if not doc.status:
		frappe.throw(_("Enter the readings: the inspection has no result yet."), title=_("Not inspected"))


def qi_on_submit(doc, method=None):
	if doc.status != "Rejected" or doc.non_conformance:
		return
	failed = [r.specification for r in doc.readings if r.status == "Rejected"]
	where = frappe.db.get_value("Task", doc.task, "subject") if doc.task else (doc.item_name or doc.item_code)
	nc = frappe.get_doc({
		"doctype": "Non Conformance", "status": "Open", "raised_on": doc.report_date or today(),
		"subject": _("{0}: {1} rejected").format(where or doc.name, checks(failed))[:140],
		"project": doc.project, "wbs": doc.wbs, "task": doc.task, "quality_inspection": doc.name,
		"details": _("Raised from inspection {0} ({1}). Failed: {2}. {3}").format(
			doc.name, doc.request_no or doc.inspection_type, ", ".join(failed) or "-", doc.remarks or ""),
	})
	nc.flags.ignore_permissions = True
	nc.insert()
	doc.db_set("non_conformance", nc.name)
	frappe.msgprint(_("Non Conformance {0} raised.").format(frappe.utils.get_link_to_form("Non Conformance", nc.name)),
	                indicator="orange", alert=True)


def checks(failed) -> str:
	if not failed:
		return _("inspection")
	return ", ".join(failed) if len(failed) <= 2 else _("{0} and {1} more").format(", ".join(failed[:2]), len(failed) - 2)


def next_request_no(project) -> str:
	last = frappe.db.sql("""select max(cast(substring(request_no, 4) as unsigned)) from `tabQuality Inspection`
		where project = %s and request_no like 'IR-%%'""", project)[0][0]
	return f"IR-{cint(last) + 1:04d}"


@frappe.whitelist()
def request_inspection(task: str, inspection_point: str = "Hold", report_date: str | None = None, inspected_by: str | None = None) -> str:
	"""A draft inspection of the task's work, with its task type's checklist."""
	t = frappe.get_doc("Task", task)
	t.check_permission("read")
	frappe.has_permission("Quality Inspection", "create", throw=True)
	if not t.type:
		frappe.throw(_("Set the task's type first: its checklist comes from the task type."), title=_("Task type"))
	template = frappe.db.get_value("Task Type", t.type, "quality_inspection_template")
	if not template:
		frappe.throw(_("Task type {0} has no Quality Inspection Template: add one to the task type.").format(t.type), title=_("Checklist"))
	qi = frappe.get_doc({"doctype": "Quality Inspection", "inspection_type": "In Process", "report_date": report_date or today(),
	                     "project": t.project, "wbs": t.wbs, "task": t.name, "inspection_point": inspection_point,
	                     "inspected_by": inspected_by or frappe.session.user, "quality_inspection_template": template,
	                     "company": frappe.db.get_value("Project", t.project, "company"),
	                     "description": t.subject})
	qi.get_item_specification_details()
	qi.insert()
	return qi.name


# ---------------------------------------------------------------- NCR

def nc_validate(doc, method=None):
	if doc.get("quality_inspection") and not (doc.project and doc.task):
		qi = frappe.db.get_value("Quality Inspection", doc.quality_inspection, ["project", "wbs", "task"], as_dict=True)
		doc.project, doc.wbs, doc.task = doc.project or qi.project, doc.wbs or qi.wbs, doc.task or qi.task
	if doc.get("task"):
		project, wbs = frappe.db.get_value("Task", doc.task, ["project", "wbs"])
		if doc.project and doc.project != project:
			frappe.throw(_("Task {0} is on {1}, not {2}.").format(doc.task, project, doc.project))
		doc.project, doc.wbs = project, doc.wbs or wbs
	if doc.wbs and doc.project and frappe.db.get_value("WBS", doc.wbs, "project") != doc.project:
		frappe.throw(_("WBS {0} is not part of {1}.").format(doc.wbs, doc.project))
	doc.raised_on = doc.raised_on or today()
	if doc.due_date and getdate(doc.due_date) < getdate(doc.raised_on):
		frappe.throw(_("The due date is before the day the NCR was raised."))
	if doc.status in ("Action Taken", "Closed") and not text(doc.corrective_action):
		frappe.throw(_("Record the corrective action before marking it {0}.").format(_(doc.status)), title=_("Corrective action"))
	if doc.status == "Closed":
		doc.closed_on = doc.closed_on or today()
	else:
		doc.closed_on = None


def text(html) -> str:
	return frappe.utils.strip_html(html or "").strip()
