# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Resource-loaded tasks - catalogue 6.3.

A task lists what it needs: labour (people a day, by crew or trade), equipment
(machines a day, by asset or category) and materials (quantity, needed by a date).
Each row runs for a number of days (the task's duration unless set); its total is
qty a day × days. A task's crew sets its foreman and the headcount of its labour
row.

"Fill from estimate" builds the rows from the Estimate Sheet of the task's BOQ line
(P-02C), scaled to the task's planned quantity: labour and equipment take the
estimate's daily output to find the days (planned qty ÷ output a day); materials
take the quantity per unit, with wastage. Subcontract and other rows are not
resources on site and are left out, and so is an equipment row that names no
machine (fuel, say).
"""

import math
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

# Words in an estimate's description that tell the trade of a labour row.
TRADE_WORDS = [("tile", "Tiling"), ("tiling", "Tiling"), ("mason", "Masonry"), ("block", "Masonry"), ("concrete", "Concrete"),
               ("steel fix", "Steel fixing"), ("formwork", "Formwork"), ("carpent", "Carpentry"), ("window", "Carpentry"),
               ("joiner", "Carpentry"), ("electric", "Electrical"), ("plumb", "Plumbing"), ("paint", "Painting"),
               ("operator", "Plant operators"), ("labour", "General labour"), ("helper", "General labour"), ("banksman", "General labour")]
# ... and the category of an equipment row.
MACHINE_WORDS = [("excavator", "Heavy Equipment"), ("dozer", "Heavy Equipment"), ("crane", "Heavy Equipment"), ("loader", "Heavy Equipment"),
                 ("roller", "Heavy Equipment"), ("mixer", "Small Machinery"), ("vibrator", "Small Machinery"), ("compactor", "Small Machinery"),
                 ("pump", "Small Machinery"), ("generator", "Small Machinery")]


def task_days(task) -> int:
	if not task.exp_start_date or not task.exp_end_date:
		return 0
	return 1 if cint(task.is_milestone) else (getdate(task.exp_end_date) - getdate(task.exp_start_date)).days + 1


def validate(doc, method=None):
	if doc.crew:
		crew = frappe.db.get_value("Crew", doc.crew, ["foreman", "headcount", "trade"], as_dict=True)
		doc.foreman = doc.foreman or (crew.foreman if crew else None)
	if doc.boq and not doc.boq_item and doc.wbs:
		wbs_boq, wbs_line = frappe.db.get_value("WBS", doc.wbs, ["boq", "boq_item"]) or (None, None)
		if wbs_boq == doc.boq:
			doc.boq_item = wbs_line
	if not doc.boq and doc.wbs:
		doc.boq, doc.boq_item = frappe.db.get_value("WBS", doc.wbs, ["boq", "boq_item"]) or (None, None)
	doc.boq_line = line_label(doc.boq_item) if doc.boq_item else None
	days = task_days(doc)
	for row in doc.get("resources") or []:
		if row.resource_type == "Labour":
			row.crew = row.crew or (doc.crew if not any(r.crew for r in doc.resources if r is not row) else None)
			if row.crew:
				crew = frappe.db.get_value("Crew", row.crew, ["headcount", "trade"], as_dict=True)
				row.trade = row.trade or crew.trade
				row.qty_per_day = flt(row.qty_per_day) or flt(crew.headcount)
				row.description = row.description or _("Crew {0}").format(frappe.db.get_value("Crew", row.crew, "crew_name"))
		elif row.resource_type == "Equipment" and row.asset and not row.asset_category:
			row.asset_category = frappe.db.get_value("Asset", row.asset, "asset_category")
		elif row.resource_type == "Material":
			row.need_by_date = row.need_by_date or doc.exp_start_date
			if row.item_code and not row.uom:
				row.uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
		row.days = cint(row.days) or days
		row.total_qty = flt(flt(row.qty_per_day) * cint(row.days), 3)


def line_label(boq_item):
	line = frappe.db.get_value("BOQ Item", boq_item, ["boq_ref", "description", "item_name"], as_dict=True)
	if not line:
		return None
	return " · ".join(x for x in (line.boq_ref, (line.description or line.item_name or "")[:100]) if x)


@frappe.whitelist()
def boq_lines(boq: str) -> list[dict]:
	frappe.has_permission("BOQ", "read", doc=boq, throw=True)
	return frappe.get_all("BOQ Item", filters={"parent": boq, "parenttype": "BOQ", "is_allowance": 0},
	                      fields=["name", "boq_ref", "description", "item_name", "boq_qty", "uom"], order_by="idx")


def estimate_for(boq, boq_item):
	"""The line's own estimate, else the estimate of the same line (by ref) on another
	BOQ of the same award: a budget BOQ's lines were priced on the tender."""
	if not boq_item:
		return None
	own = frappe.db.get_value("Estimate Sheet", {"boq": boq, "boq_item": boq_item, "docstatus": ["<", 2]}, "name")
	if own:
		return own
	ref = frappe.db.get_value("BOQ Item", boq_item, "boq_ref")
	award = frappe.db.get_value("BOQ", boq, "awarded_quotation")
	if not ref or not award:
		return None
	boqs = set(frappe.get_all("BOQ", filters={"awarded_quotation": award, "docstatus": ["<", 2], "name": ["!=", boq]}, pluck="name"))
	boqs |= set(frappe.get_all("Awarded Quotation Component", filters={"parent": award, "boq": ["is", "set"]}, pluck="boq"))
	if not boqs:
		return None
	return frappe.db.get_value("Estimate Sheet", {"boq": ["in", list(boqs)], "boq_ref": ref, "docstatus": ["<", 2]}, "name")


def guess(words, text):
	text = (text or "").lower()
	return next((value for word, value in words if word in text), None)


@frappe.whitelist()
def fill_from_estimate(task: str) -> dict:
	"""Replace the task's estimate-made rows with those of its BOQ line's estimate."""
	t = frappe.get_doc("Task", task)
	t.check_permission("write")
	if not t.boq_item:
		frappe.throw(_("Pick the task's BOQ line first."), title=_("Fill from estimate"))
	if not flt(t.planned_qty):
		frappe.throw(_("Enter the task's planned quantity: the estimate is scaled to it."), title=_("Fill from estimate"))
	sheet = estimate_for(t.boq, t.boq_item)
	if not sheet:
		frappe.throw(_("BOQ line {0} has no estimate sheet.").format(t.boq_line or t.boq_item), title=_("Fill from estimate"))
	est = frappe.get_doc("Estimate Sheet", sheet)
	duration = task_days(t)
	rows, skipped, long_rows = [], [], []
	for r in est.resources:
		desc = r.description or r.item_code or r.resource_type
		if r.resource_type == "Labour":
			if not flt(r.output_per_day):
				skipped.append(desc); continue
			days = math.ceil(flt(t.planned_qty) / flt(r.output_per_day))
			heads = re.search(r"\((\d+)\)", desc or "")
			rows.append({"resource_type": "Labour", "description": desc, "trade": guess(TRADE_WORDS, desc) or "General labour",
			             "qty_per_day": int(heads.group(1)) if heads else 1, "uom": "Nos", "days": days})
		elif r.resource_type == "Equipment":
			asset_id = re.search(r"\(([A-Z]{2,4}-\d{3,5})\)", desc or "")
			asset = asset_id.group(1) if asset_id and frappe.db.exists("Asset", asset_id.group(1)) else None
			category = frappe.db.get_value("Asset", asset, "asset_category") if asset else guess(MACHINE_WORDS, desc)
			if not category or not flt(r.output_per_day):
				skipped.append(desc); continue
			rows.append({"resource_type": "Equipment", "description": desc, "asset": asset, "asset_category": category, "qty_per_day": 1,
			             "uom": "Nos", "days": math.ceil(flt(t.planned_qty) / flt(r.output_per_day))})
		elif r.resource_type == "Material":
			total = flt(r.qty_per_unit) * flt(t.planned_qty) * (1 + flt(r.wastage_percent) / 100)
			if not total:
				skipped.append(desc); continue
			rows.append({"resource_type": "Material", "description": desc, "item_code": r.item_code, "uom": r.uom, "days": duration or 1,
			             "qty_per_day": flt(total / (duration or 1), 6), "need_by_date": t.exp_start_date})
		else:
			skipped.append(desc)
	for row in rows:
		row["estimate_sheet"] = sheet
		if row["resource_type"] in ("Labour", "Equipment") and duration and row["days"] > duration:
			long_rows.append(_("{0}: {1} days in a {2}-day task").format(row["description"], row["days"], duration))
	t.set("resources", [r for r in t.resources if r.estimate_sheet != sheet] + rows)
	t.flags.ignore_permissions = True
	t.save()
	return {"estimate_sheet": sheet, "rows": len(rows), "skipped": skipped, "too_long": long_rows}


# ---------------------------------------------------------------- loading

def resource_loading(project=None, from_date=None, to_date=None, company=None, resource_type=None) -> list[dict]:
	"""What the tasks need, day by day: one row per task resource per day it runs,
	{date, resource_type, group, qty, uom, task, project}. Labour is grouped by trade
	(people), equipment by asset category (machines), materials by item on their need-by
	date (the whole quantity). Read by Resource Loading (P-06B), procurement planning
	(P-05A), the equipment plan (P-08B) and the manpower histogram (P-13E)."""
	conditions = ["t.status not in ('Cancelled', 'Completed', 'Template')", "t.is_template = 0"]
	values = {}
	if project:
		conditions.append("t.project = %(project)s"); values["project"] = project
	if company:
		conditions.append("t.company = %(company)s"); values["company"] = company
	if resource_type:
		conditions.append("r.resource_type = %(rtype)s"); values["rtype"] = resource_type
	rows = frappe.db.sql(f"""select r.resource_type, r.trade, r.asset_category, r.item_code, r.description, r.qty_per_day, r.days, r.uom,
			r.total_qty, r.need_by_date, t.name task, t.project, t.exp_start_date
		from `tabTask Resource` r join `tabTask` t on t.name = r.parent and r.parenttype = 'Task'
		where {' and '.join(conditions)}""", values, as_dict=True)
	start, end = getdate(from_date) if from_date else None, getdate(to_date) if to_date else None
	out = []
	for r in rows:
		if r.resource_type == "Material":
			when = getdate(r.need_by_date or r.exp_start_date)
			if (start and when < start) or (end and when > end):
				continue
			out.append({"date": when, "resource_type": "Material", "group": r.item_code or r.description, "qty": flt(r.total_qty),
			            "uom": r.uom, "task": r.task, "project": r.project})
			continue
		if not r.exp_start_date:
			continue
		group = (r.trade or _("Unassigned")) if r.resource_type == "Labour" else (r.asset_category or _("Unassigned"))
		first = getdate(r.exp_start_date)
		for i in range(cint(r.days)):
			when = frappe.utils.add_days(first, i)
			when = getdate(when)
			if (start and when < start) or (end and when > end):
				continue
			out.append({"date": when, "resource_type": r.resource_type, "group": group, "qty": flt(r.qty_per_day), "uom": r.uom,
			            "task": r.task, "project": r.project})
	return out
