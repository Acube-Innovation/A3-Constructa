# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""NCR Register - catalogue 6.8: the non-conformances still open, by WBS.

One row per NCR, grouped under its WBS node (in tree order): status, the
inspection and task it came from, days open (age), the action owner and due date
(overdue days once past), and the cost impact. Closed NCRs are left out unless
asked for. Filters: project, WBS (and below), action owner.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = ncrs(filters)
	return columns(filters), rows, None, chart(rows), summary(rows)


def ncrs(filters) -> list[dict]:
	conditions, values = ["1 = 1"], {}
	if not filters.get("include_closed"):
		conditions.append("nc.status != 'Closed'")
	if filters.get("project"):
		conditions.append("nc.project = %(project)s"); values["project"] = filters.project
	if filters.get("wbs"):
		lft, rgt = frappe.db.get_value("WBS", filters.wbs, ["lft", "rgt"]) or (0, 0)
		conditions.append("nc.wbs in (select name from `tabWBS` where lft >= %(lft)s and rgt <= %(rgt)s)")
		values.update(lft=lft, rgt=rgt)
	if filters.get("action_owner"):
		conditions.append("nc.action_owner = %(owner)s"); values["owner"] = filters.action_owner
	permitted = frappe.get_list("Non Conformance", pluck="name", limit_page_length=0)
	if not permitted:
		return []
	values["permitted"] = permitted
	rows = frappe.db.sql(f"""select nc.name, nc.subject, nc.status, nc.project, nc.wbs, w.wbs_name, nc.task, t.subject task_subject,
			nc.quality_inspection, qi.inspection_point, nc.raised_on, nc.action_owner, nc.action_owner_name, nc.due_date,
			nc.closed_on, nc.cost_impact, w.lft
		from `tabNon Conformance` nc
		left join `tabWBS` w on w.name = nc.wbs
		left join `tabTask` t on t.name = nc.task
		left join `tabQuality Inspection` qi on qi.name = nc.quality_inspection
		where {' and '.join(conditions)} and nc.name in %(permitted)s
		order by w.lft is null, w.lft, nc.raised_on""", values, as_dict=True)
	now = getdate(today())
	for r in rows:
		end = getdate(r.closed_on) if r.closed_on else now
		r.age = date_diff(end, r.raised_on) if r.raised_on else None
		r.overdue = max(date_diff(now, r.due_date), 0) if r.due_date and r.status != "Closed" else 0
		r.wbs_label = f"{r.wbs} · {r.wbs_name}" if r.wbs else _("No WBS")
	return rows


def columns(filters):
	cols = [
		{"fieldname": "wbs_label", "label": _("WBS"), "fieldtype": "Data", "width": 210},
		{"fieldname": "name", "label": _("NCR"), "fieldtype": "Link", "options": "Non Conformance", "width": 120},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 260},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 105},
	]
	if not filters.get("project"):
		cols.append({"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100})
	cols += [
		{"fieldname": "raised_on", "label": _("Raised"), "fieldtype": "Date", "width": 100},
		{"fieldname": "age", "label": _("Age (days)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "action_owner_name", "label": _("Action Owner"), "fieldtype": "Data", "width": 150},
		{"fieldname": "due_date", "label": _("Due"), "fieldtype": "Date", "width": 100},
		{"fieldname": "overdue", "label": _("Overdue (days)"), "fieldtype": "Int", "width": 110},
		{"fieldname": "cost_impact", "label": _("Cost Impact"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "task_subject", "label": _("Task"), "fieldtype": "Data", "width": 170},
		{"fieldname": "quality_inspection", "label": _("Inspection"), "fieldtype": "Link", "options": "Quality Inspection", "width": 150},
		{"fieldname": "inspection_point", "label": _("Point"), "fieldtype": "Data", "width": 90},
		{"fieldname": "closed_on", "label": _("Closed"), "fieldtype": "Date", "width": 100},
	]
	return cols


def chart(rows):
	open_rows = [r for r in rows if r.status != "Closed"]
	if not open_rows:
		return None
	by = {}
	for r in open_rows:
		label = r.wbs_name or _("No WBS")
		by[label] = by.get(label, 0) + flt(r.cost_impact)
	return {"data": {"labels": list(by), "datasets": [{"name": _("Open cost impact"), "values": list(by.values())}]},
	        "type": "bar", "fieldtype": "Currency", "colors": ["#e8590c"]}


def summary(rows):
	open_rows = [r for r in rows if r.status != "Closed"]
	overdue = [r for r in open_rows if r.overdue]
	return [
		{"label": _("Open NCRs"), "value": len(open_rows), "datatype": "Int", "indicator": "Red" if open_rows else "Green"},
		{"label": _("Overdue"), "value": len(overdue), "datatype": "Int", "indicator": "Red" if overdue else "Green"},
		{"label": _("Oldest open (days)"), "value": max((r.age or 0 for r in open_rows), default=0), "datatype": "Int"},
		{"label": _("Open cost impact"), "value": sum(flt(r.cost_impact) for r in open_rows), "datatype": "Currency"},
	]
