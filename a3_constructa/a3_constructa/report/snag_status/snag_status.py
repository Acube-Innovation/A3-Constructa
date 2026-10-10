# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Snag Status - catalogue 6.11: how far snagging has got, by WBS and trade.

Per WBS node and trade: snags open, fixed (waiting for the check) and verified,
the share verified, and how many open or fixed snags are past their due date.
Filters: project, WBS (and below), trade.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = data(filters)
	return columns(filters), rows, None, chart(rows), summary(rows)


def data(filters):
	conditions, values = ["1 = 1"], {"today": getdate(today())}
	if filters.get("project"):
		conditions.append("l.project = %(project)s"); values["project"] = filters.project
	if filters.get("wbs"):
		lft, rgt = frappe.db.get_value("WBS", filters.wbs, ["lft", "rgt"]) or (0, 0)
		conditions.append("l.wbs in (select name from `tabWBS` where lft >= %(lft)s and rgt <= %(rgt)s)")
		values.update(lft=lft, rgt=rgt)
	if filters.get("trade"):
		conditions.append("i.trade = %(trade)s"); values["trade"] = filters.trade
	permitted = frappe.get_list("Snag List", pluck="name", limit_page_length=0)
	if not permitted:
		return []
	values["permitted"] = permitted
	rows = frappe.db.sql(f"""select l.project, l.wbs, w.wbs_name, coalesce(nullif(i.trade, ''), %(none)s) trade,
			sum(i.status = 'Open') open, sum(i.status = 'Fixed') fixed, sum(i.status = 'Verified') verified, count(*) total,
			sum(i.status != 'Verified' and i.due_date < %(today)s) overdue
		from `tabSnag Item` i join `tabSnag List` l on l.name = i.parent left join `tabWBS` w on w.name = l.wbs
		where {' and '.join(conditions)} and l.name in %(permitted)s
		group by l.project, l.wbs, w.wbs_name, w.lft, trade
		order by l.project, w.lft is null, w.lft, trade""", {**values, "none": _("Unassigned")}, as_dict=True)
	for r in rows:
		r.verified_percent = flt(flt(r.verified) / r.total * 100, 1) if r.total else 0
		r.wbs_label = f"{r.wbs} · {r.wbs_name}" if r.wbs else _("No WBS")
	return rows


def columns(filters):
	cols = []
	if not filters.get("project"):
		cols.append({"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100})
	return cols + [
		{"fieldname": "wbs_label", "label": _("WBS"), "fieldtype": "Data", "width": 240},
		{"fieldname": "trade", "label": _("Trade"), "fieldtype": "Data", "width": 120},
		{"fieldname": "open", "label": _("Open"), "fieldtype": "Int", "width": 80},
		{"fieldname": "fixed", "label": _("Fixed"), "fieldtype": "Int", "width": 80},
		{"fieldname": "verified", "label": _("Verified"), "fieldtype": "Int", "width": 85},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 75},
		{"fieldname": "verified_percent", "label": _("% Verified"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "overdue", "label": _("Overdue"), "fieldtype": "Int", "width": 85},
	]


def chart(rows):
	trades = {}
	for r in rows:
		t = trades.setdefault(r.trade, [0, 0, 0])
		t[0] += int(r.open); t[1] += int(r.fixed); t[2] += int(r.verified)
	if not trades:
		return None
	return {"data": {"labels": list(trades), "datasets": [{"name": _("Open"), "values": [v[0] for v in trades.values()]},
	                                                       {"name": _("Fixed"), "values": [v[1] for v in trades.values()]},
	                                                       {"name": _("Verified"), "values": [v[2] for v in trades.values()]}]},
	        "type": "bar", "barOptions": {"stacked": 1}, "colors": ["#e03131", "#f08c00", "#2f9e44"]}


def summary(rows):
	tot = lambda k: sum(int(r[k] or 0) for r in rows)  # noqa: E731
	total = tot("total")
	return [
		{"label": _("Open"), "value": tot("open"), "datatype": "Int", "indicator": "Red" if tot("open") else "Green"},
		{"label": _("Fixed, awaiting check"), "value": tot("fixed"), "datatype": "Int", "indicator": "Orange" if tot("fixed") else "Green"},
		{"label": _("Verified"), "value": tot("verified"), "datatype": "Int", "indicator": "Green"},
		{"label": _("% Verified"), "value": f"{tot('verified') / total * 100:.0f}%" if total else "-", "datatype": "Data"},
		{"label": _("Overdue"), "value": tot("overdue"), "datatype": "Int", "indicator": "Red" if tot("overdue") else "Green"},
	]
