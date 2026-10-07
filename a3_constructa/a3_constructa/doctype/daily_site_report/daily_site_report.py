# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Daily Site Report - catalogues 6.7 and 7.8: one site's day, filed once.

One report per project, site and date: the weather, the labour (crews or single
workers on tasks), subcontractors, plant, the quantities done, materials used,
delays, visitors and photos.

Submitting it books the day, in the one transaction, each record linked back to
its row:
1. labour → a Timesheet per worker (a crew's hours split over its active members
   by split_crew_hours, P-07A), each line with project, task, WBS and cost code;
   a worker's lines run one after another from the start of the site day (or
   after hours already booked that day on another report), and overtime follows
   at 1.5 times the rate;
2. equipment → an Equipment Log per machine (P-08A: meter, hours, internal charge);
3. progress → a row in each task's progress log, source Daily Site Report (P-06D);
4. materials → one Material Issue Note (MIN) from the site store.
Cancelling the report cancels all of it and takes its rows out of the progress logs.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, get_datetime, getdate, today

from a3_constructa.a3_constructa.doctype.crew.crew import DAY_START, DEFAULT_ACTIVITY, daily_wage, split_crew_hours, standard_hours

MIN = "Material Issue Note (MIN)"
SOURCE = "Daily Site Report"
OVERTIME_FACTOR = 1.5


class DailySiteReport(Document):
	def before_insert(self):
		if not self.prepared_by:
			self.prepared_by = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name")
		if self.prepared_by:
			self.prepared_by_name = frappe.db.get_value("Employee", self.prepared_by, "employee_name")

	def validate(self):
		self.check_unique()
		if getdate(self.report_date) > getdate(today()):
			frappe.throw(_("A site report is for a day that has happened: {0} is in the future.").format(
				frappe.format(self.report_date, {"fieldtype": "Date"})))
		self.check_labour()
		self.check_equipment()
		from a3_constructa.overrides.certificates import site_report_validate

		site_report_validate(self)
		self.check_progress()
		self.check_materials()
		self.totals()
		self.title = title(self.project, self.report_date)

	# ------------------------------------------------------------ checks

	def check_unique(self):
		other = frappe.db.get_value("Daily Site Report", {"project": self.project, "site": self.site or ["is", "not set"],
		                                                  "report_date": self.report_date, "docstatus": ["<", 2],
		                                                  "name": ["!=", self.name or ""]}, "name")
		if other:
			frappe.throw(_("{0} already has a site report for {1} on {2}: {3}.").format(
				self.project, self.site or _("this site"), frappe.format(self.report_date, {"fieldtype": "Date"}), other), title=_("Duplicate"))

	def check_task(self, row, label):
		if not row.get("task"):
			return
		project, wbs = frappe.db.get_value("Task", row.task, ["project", "wbs"])
		if project != self.project:
			frappe.throw(_("{0} row {1}: task {2} is not on {3}.").format(label, row.idx, row.task, self.project))
		if row.meta.has_field("wbs") and not row.get("wbs"):
			row.wbs = wbs

	def check_wbs(self, row, label):
		if row.get("wbs") and frappe.db.get_value("WBS", row.wbs, "project") != self.project:
			frappe.throw(_("{0} row {1}: WBS {2} is not part of {3}.").format(label, row.idx, row.wbs, self.project))

	def check_labour(self):
		for row in self.labour:
			if not row.crew and not row.employee:
				frappe.throw(_("Labour row {0}: choose a crew or a worker.").format(row.idx))
			if flt(row.hours) <= 0:
				frappe.throw(_("Labour row {0}: enter the hours worked.").format(row.idx))
			if flt(row.hours) + flt(row.overtime_hours) > 24:
				frappe.throw(_("Labour row {0}: {1} hours with overtime; a day has 24.").format(row.idx, flt(row.hours) + flt(row.overtime_hours)))
			if row.crew and not row.employee:
				crew = frappe.get_doc("Crew", row.crew)
				if not crew.is_active:
					frappe.throw(_("Labour row {0}: {1} is not an active crew.").format(row.idx, crew.crew_name))
				row.headcount = sum(1 for m in crew.members if m.is_active)
				if not row.headcount:
					frappe.throw(_("Labour row {0}: {1} has no active members to book.").format(row.idx, crew.crew_name))
			else:
				row.headcount = 1
			self.check_task(row, _("Labour"))
			self.check_wbs(row, _("Labour"))

	def check_equipment(self):
		seen = set()
		for row in self.equipment:
			if row.asset in seen:
				frappe.throw(_("Equipment row {0}: {1} is listed twice; one row per machine a day.").format(row.idx, row.asset_name or row.asset))
			seen.add(row.asset)
			if flt(row.worked_hours) + flt(row.idle_hours) + flt(row.breakdown_hours) > 24:
				frappe.throw(_("Equipment row {0}: worked, idle and breakdown hours pass 24.").format(row.idx))
			if row.cost_code and frappe.db.get_value("Cost Code", row.cost_code, "category") != "Equipment":
				frappe.throw(_("Equipment row {0}: plant is charged to an Equipment cost code, not {1}.").format(row.idx, row.cost_code))
			self.check_task(row, _("Equipment"))
			self.check_wbs(row, _("Equipment"))

	def check_progress(self):
		for row in self.progress:
			if flt(row.qty_done) <= 0:
				frappe.throw(_("Progress row {0}: enter the quantity done.").format(row.idx))
			self.check_task(row, _("Progress"))

	def check_materials(self):
		store = project_store(self.project)
		for row in self.materials:
			if flt(row.qty) <= 0:
				frappe.throw(_("Materials row {0}: enter the quantity used.").format(row.idx))
			row.warehouse = row.warehouse or store
			if not row.warehouse:
				frappe.throw(_("Materials row {0}: choose the site store; {1} has no store linked to it.").format(row.idx, self.project))
			self.check_wbs(row, _("Materials"))

	def totals(self):
		self.total_hours = flt(sum(flt(r.hours) * cint(r.headcount) for r in self.labour), 2)
		self.total_overtime_hours = flt(sum(flt(r.overtime_hours) * cint(r.headcount) for r in self.labour), 2)
		crews = {}
		for r in self.labour:
			key = r.employee or r.crew
			crews[key] = max(crews.get(key, 0), cint(r.headcount))
		self.total_headcount = sum(crews.values()) + sum(cint(r.headcount) for r in self.subcontractors)
		self.hours_lost = flt(sum(flt(r.hours_lost) for r in self.delays), 2)

	# ------------------------------------------------------------ submit

	def before_submit(self):
		missing = [str(r.idx) for r in self.equipment if not flt(r.meter_end)]
		if missing:
			frappe.throw(_("Equipment rows {0}: enter the evening meter reading.").format(", ".join(missing)), title=_("Meter"))
		if not (self.labour or self.equipment or self.progress or self.materials):
			frappe.throw(_("Nothing to book: add the day's labour, equipment, progress or materials."))

	def on_submit(self):
		self.book_labour()
		self.book_equipment()
		self.book_progress()
		self.issue_materials()

	def book_labour(self):
		day = standard_hours()
		cursor = {}  # employee -> next free time on the day
		lines = {}  # employee -> [time log]
		rows_of = {}  # employee -> {labour row names}
		activity = DEFAULT_ACTIVITY if frappe.db.exists("Activity Type", DEFAULT_ACTIVITY) else None
		for row in self.labour:
			for part, hours, factor in (("normal", flt(row.hours), 1), ("overtime", flt(row.overtime_hours), OVERTIME_FACTOR)):
				if hours <= 0:
					continue
				for line in self.workers(row, hours, day, activity):
					emp = line["employee"]
					start = cursor.get(emp) or self.day_start(emp)
					end = add_to_date(start, hours=hours)
					cursor[emp] = end
					rate = flt(flt(line["costing_rate"]) * factor, 4)
					lines.setdefault(emp, []).append({
						"activity_type": line.get("activity_type"), "from_time": start, "to_time": end, "hours": hours,
						"project": self.project, "task": row.task, "wbs": row.wbs, "cost_code": row.cost_code,
						"costing_rate": rate, "costing_amount": flt(rate * hours, 2), "is_billable": 0,
						"description": line["description"] + (" - " + _("overtime") if part == "overtime" else "") + f" ({self.name})"})
					rows_of.setdefault(emp, set()).add(row.name)
		made = {}
		for emp, logs in lines.items():
			ts = frappe.get_doc({"doctype": "Timesheet", "company": self.company, "employee": emp, "parent_project": self.project,
			                     "daily_site_report": self.name, "time_logs": logs,
			                     "note": _("From Daily Site Report {0}").format(self.name)})
			ts.flags.ignore_permissions = True
			ts.insert()
			ts.submit()
			for r in rows_of[emp]:
				made.setdefault(r, []).append(ts.name)
		for row in self.labour:
			row.db_set("timesheets", ", ".join(made.get(row.name, [])))

	def day_start(self, employee):
		"""07:00, or after the hours the worker already has booked that day (another site's report)."""
		start = get_datetime(f"{self.report_date} {DAY_START}")
		booked = frappe.db.sql("""select max(d.to_time) from `tabTimesheet Detail` d join `tabTimesheet` t on t.name = d.parent
			where t.employee = %s and t.docstatus = 1 and date(d.from_time) = %s""", (employee, self.report_date))[0][0]
		return max(start, get_datetime(booked)) if booked else start

	def workers(self, row, hours, day, activity):
		if row.crew and not row.employee:
			return split_crew_hours(row.crew, self.report_date, hours, project=self.project, task=row.task, wbs=row.wbs,
			                        cost_code=row.cost_code)
		rate = 0.0
		if row.crew:
			rate = flt(frappe.db.get_value("Crew Member", {"parent": row.crew, "employee": row.employee}, "daily_rate"))
		rate = rate or daily_wage(row.employee, self.report_date)
		name = frappe.db.get_value("Employee", row.employee, "employee_name")
		return [{"employee": row.employee, "costing_rate": flt(rate / day, 4) if day else 0, "activity_type": activity,
		         "description": name or row.employee}]

	def book_equipment(self):
		for row in self.equipment:
			log = frappe.get_doc({"doctype": "Equipment Log", "asset": row.asset, "log_date": self.report_date, "project": self.project,
			                      "operator": row.get("operator"),
			                      "site": self.site, "wbs": row.wbs, "cost_code": row.cost_code, "meter_start": row.meter_start,
			                      "meter_end": row.meter_end, "worked_hours": row.worked_hours, "idle_hours": row.idle_hours,
			                      "breakdown_hours": row.breakdown_hours, "daily_site_report": self.name,
			                      "remarks": frappe.db.get_value("Task", row.task, "subject") if row.task else None})
			log.flags.ignore_permissions = True
			log.insert()
			log.submit()
			row.db_set({"equipment_log": log.name, "meter_start": log.meter_start})

	def book_progress(self):
		from a3_constructa.overrides.task_progress import add_progress

		for row in self.progress:
			log = add_progress(row.task, self.report_date, row.qty_done, reference=self.name, source=SOURCE,
			                   remarks=_("Daily Site Report"), ignore_permissions=True)
			row.db_set("progress_log", log)

	def issue_materials(self):
		if not self.materials:
			return
		se = frappe.get_doc({"doctype": "Stock Entry", "company": self.company, "stock_entry_type": MIN, "purpose": "Material Issue",
		                     "posting_date": self.report_date, "set_posting_time": 1, "project": self.project, "daily_site_report": self.name,
		                     "remarks": _("Used on site, Daily Site Report {0}").format(self.name),
		                     "items": [{"item_code": r.item_code, "qty": r.qty, "s_warehouse": r.warehouse, "project": self.project,
		                                "wbs": r.wbs, "cost_code": r.cost_code} for r in self.materials]})
		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		for row, line in zip(self.materials, se.items):
			row.db_set("stock_entry_detail", line.name)
		self.db_set("material_issue", se.name)

	# ------------------------------------------------------------ cancel

	def before_cancel(self):
		# The records this report made link back to it; they are cancelled with it below.
		self.ignore_linked_doctypes = ("Timesheet", "Stock Entry", "Equipment Log")

	def on_cancel(self):
		if self.material_issue and frappe.db.get_value("Stock Entry", self.material_issue, "docstatus") == 1:
			cancel("Stock Entry", self.material_issue)
		for row in self.equipment:
			if row.equipment_log and frappe.db.get_value("Equipment Log", row.equipment_log, "docstatus") == 1:
				cancel("Equipment Log", row.equipment_log)
		for name in frappe.get_all("Timesheet", filters={"daily_site_report": self.name, "docstatus": 1}, pluck="name"):
			cancel("Timesheet", name)
		from a3_constructa.overrides.task_progress import remove_progress

		for task in {r.task for r in self.progress}:
			remove_progress(task, self.name)


def title(project, on):
	return f"{frappe.db.get_value('Project', project, 'project_name') or project} · {frappe.format(on, {'fieldtype': 'Date'})}"


def cancel(doctype, name):
	doc = frappe.get_doc(doctype, name)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.cancel()


def project_store(project):
	"""The project's site store (Warehouse.project, P-06E)."""
	stores = frappe.get_all("Warehouse", filters={"project": project, "is_group": 0, "disabled": 0}, pluck="name", order_by="creation")
	return stores[0] if stores else None


@frappe.whitelist()
def defaults(project: str) -> dict:
	"""What a new report on the project starts with: its site and store."""
	frappe.has_permission("Project", "read", doc=project, throw=True)
	return {"site": frappe.db.get_value("Project", project, "location"), "store": project_store(project)}
