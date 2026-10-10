# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Procurement Plan - catalogue 5.4: what to buy, and when to ask for it.

recommended_pr_date = required on site - lead time (build sheet head 21 row 20).

The plan follows the schedule (P-05A):
- "Refresh from schedule" adds a line per material on the project's tasks (Task
  Resource, P-06B): required on site = task start - the site buffer (A3
  Constructa Settings, 7 days), the item's lead time, the task's WBS and cost
  code. A line is kept per task and item and updated on each refresh; one whose
  task no longer needs the item goes, unless something was already requested.
  Lines typed in by hand (no task) are left alone.
- When a task's start moves, its lines move with it (on_task_update).
- A line is linked to the material request raised for it (or, failing that, one
  for the same item on the project), and flagged pr_overdue when its PR date has
  passed with nothing requested or ordered. The Planning overview's
  needs-attention check reads the flag; a daily job keeps it current.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, today

CLOSED = ("Cancelled", "Completed")


class ProcurementPlan(Document):
	def validate(self):
		self.set_recommended_pr_date()
		for row in self.items:
			if row.task and frappe.db.get_value("Task", row.task, "project") != self.project:
				frappe.throw(_("Row {0}: task {1} is not on {2}.").format(row.idx, row.task, self.project))
		link_requests(self)

	def set_recommended_pr_date(self):
		"""Build sheet head 21 row 20: recommended_pr_date = required date - lead time.

		The date a purchase requisition has to be raised for the material to
		arrive on site in time. Read-only on the form, so it is derived here.
		A row with no required date has nothing to work back from and is left
		empty rather than given a date measured from today.
		"""
		for row in self.items:
			if not row.required_on_site_date:
				row.recommended_pr_date = None
				continue

			row.recommended_pr_date = add_days(
				getdate(row.required_on_site_date), -cint(row.lead_time_days)
			)

	@frappe.whitelist()
	def refresh_from_schedule(self) -> dict:
		self.check_permission("write")
		needs = schedule_needs(self.project)
		by_key = {(r.task, r.item_code): r for r in self.items if r.task}
		added = updated = 0
		for key, need in needs.items():
			row = by_key.get(key)
			if not row:
				row = self.append("items", {"task": need.task, "item_code": need.item_code, "procurement_route": "Buy",
				                            "lead_time_days": need.lead_time})
				added += 1
			else:
				updated += 1
			row.update({"anticipated_qty": need.qty, "uom": need.uom, "wbs": need.wbs or row.wbs,
			            "cost_code": need.cost_code or row.cost_code, "required_on_site_date": need.required})
			if not cint(row.lead_time_days):
				row.lead_time_days = need.lead_time
		removed, kept = [], []
		for row in list(self.items):
			if row.task and (row.task, row.item_code) not in needs:
				(kept if row.material_request else removed).append(row)
		for row in removed:
			self.remove(row)
		self.save()
		return {"added": added, "updated": updated, "removed": len(removed),
		        "kept": [f"{r.item_code} ({r.task})" for r in kept], "lines": len(self.items)}

	@frappe.whitelist()
	def make_material_request(self, rows: list | str | None = None) -> str:
		"""A draft material request for the chosen lines (or every line not yet requested and due)."""
		self.check_permission("read")
		frappe.has_permission("Material Request", "create", throw=True)
		names = frappe.parse_json(rows) if isinstance(rows, str) else rows
		lines = [r for r in self.items if (r.name in names if names else (r.pr_overdue or not r.material_request))]
		lines = [r for r in lines if not r.material_request and r.procurement_route == "Buy"]
		if not lines:
			frappe.throw(_("Nothing to request: the lines chosen are requested already, or are hired or subcontracted."))
		mr = frappe.get_doc({"doctype": "Material Request", "material_request_type": "Purchase", "company": company(self.project),
		                     "transaction_date": today(), "schedule_date": min(getdate(r.required_on_site_date or today()) for r in lines),
		                     "items": [{"item_code": r.item_code, "qty": flt(r.anticipated_qty) or 1, "uom": r.uom,
		                                "schedule_date": max(getdate(r.required_on_site_date or today()), getdate(today())),
		                                "project": self.project, "wbs": r.wbs, "cost_code": r.cost_code,
		                                "procurement_plan_item": r.name} for r in lines]})
		mr.insert()  # its on_update re-links this plan's lines (refresh_flags)
		return mr.name


def company(project):
	return frappe.db.get_value("Project", project, "company")


def buffer_days() -> int:
	value = frappe.db.get_single_value("A3 Constructa Settings", "site_buffer_days")
	return 7 if value is None else cint(value)


def schedule_needs(project) -> dict:
	"""{(task, item): need} for the materials on the project's open tasks."""
	rows = frappe.db.sql("""select t.name task, t.exp_start_date, t.wbs, t.cost_code, r.item_code, sum(r.total_qty) qty, r.uom,
			i.lead_time_days lead_time, i.stock_uom
		from `tabTask Resource` r join `tabTask` t on t.name = r.parent and r.parenttype = 'Task'
		join `tabItem` i on i.name = r.item_code
		where t.project = %s and t.is_template = 0 and t.status not in ('Cancelled', 'Completed', 'Template')
			and r.resource_type = 'Material' and r.item_code is not null and t.exp_start_date is not null
		group by t.name, r.item_code order by t.exp_start_date, t.name, r.item_code""", project, as_dict=True)
	buffer = buffer_days()
	out = {}
	for r in rows:
		r.required = add_days(getdate(r.exp_start_date), -buffer)
		r.uom = r.uom or r.stock_uom
		r.lead_time = cint(r.lead_time)
		out[(r.task, r.item_code)] = r
	return out


# ---------------------------------------------------------------- requests and the flag

def requested(project) -> dict:
	"""What has been asked for or ordered on the project: requests raised from plan lines,
	other requests by item, and items on purchase orders (a hire or a direct order)."""
	exclude = frappe.flags.get("a3_excluded_request") or ""
	mr_rows = frappe.db.sql("""select mr.name, i.item_code, i.procurement_plan_item from `tabMaterial Request Item` i
		join `tabMaterial Request` mr on mr.name = i.parent
		where i.project = %s and mr.docstatus < 2 and mr.status not in ('Cancelled', 'Stopped') and mr.name != %s
		order by mr.creation""", (project, exclude), as_dict=True)
	by_line = {r.procurement_plan_item: r.name for r in mr_rows if r.procurement_plan_item}
	by_item = {}
	for r in mr_rows:
		if not r.procurement_plan_item:
			by_item.setdefault(r.item_code, r.name)
	ordered = set(frappe.db.sql_list("""select distinct i.item_code from `tabPurchase Order Item` i join `tabPurchase Order` po on po.name = i.parent
		where (i.project = %s or po.project = %s) and po.docstatus < 2""", (project, project)))
	return {"line": by_line, "item": by_item, "ordered": ordered}


def link_requests(plan, req=None):
	"""A line's request is the one raised from it, else one for its item on the project that no
	plan line raised. It is overdue past its PR date with neither a request nor an order."""
	req = req or requested(plan.project)
	now = getdate(today())
	for row in plan.items:
		row.material_request = req["line"].get(row.name) or req["item"].get(row.item_code)
		asked = bool(row.material_request) or row.item_code in req["ordered"]
		row.pr_overdue = int(plan.status not in CLOSED and bool(row.recommended_pr_date)
		                     and getdate(row.recommended_pr_date) < now and not asked)


def refresh_flags(project=None):
	"""Re-link and re-flag the plans (of a project, or all): daily, and when requests change."""
	filters = {"status": ["not in", CLOSED]}
	if project:
		filters["project"] = project
	for name in frappe.get_all("Procurement Plan", filters=filters, pluck="name"):
		plan = frappe.get_doc("Procurement Plan", name)
		before = [(r.material_request, r.pr_overdue) for r in plan.items]
		link_requests(plan)
		for row, (mr, flag) in zip(plan.items, before):
			if (row.material_request, row.pr_overdue) != (mr, flag):
				row.db_set({"material_request": row.material_request, "pr_overdue": row.pr_overdue}, update_modified=False)


def daily():
	refresh_flags()


def on_request_change(doc, method=None):
	"""A material request saved, cancelled or deleted: re-link its projects' plans."""
	exclude = doc.name if method == "on_trash" else None
	for project in {r.project for r in doc.items if r.project}:
		if exclude:
			frappe.flags.a3_excluded_request = exclude
		try:
			refresh_flags(project)
		finally:
			frappe.flags.a3_excluded_request = None


# ---------------------------------------------------------------- task dates

def on_task_update(doc, method=None):
	"""A task's start moved: its plan lines follow (required = start - buffer)."""
	if not doc.has_value_changed("exp_start_date") or not doc.exp_start_date:
		return
	required = add_days(getdate(doc.exp_start_date), -buffer_days())
	rows = frappe.get_all("Procurement Plan Item", filters={"task": doc.name, "parenttype": "Procurement Plan"},
	                      fields=["name", "parent", "lead_time_days"])
	for parent in {r.parent for r in rows}:
		plan = frappe.get_doc("Procurement Plan", parent)
		if plan.status in CLOSED:
			continue
		for row in plan.items:
			if row.task == doc.name:
				row.required_on_site_date = required
		plan.flags.ignore_permissions = True
		plan.save()
