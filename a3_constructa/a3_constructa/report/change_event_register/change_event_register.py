# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Change Event Register - catalogue 3.4: open exposure by award and status.

Every change event under its award and status. An event is open exposure while
it is undecided or contested (Open, Priced, Claim): its rough cost and days may
still land on the job. Became VO, Absorbed and Closed are decided. Group rows add
up the events beneath them; the summary shows the open exposure.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today

from a3_constructa.a3_constructa.doctype.change_event.change_event import OPEN

STATUSES = ("Open", "Priced", "Claim", "Became VO", "Absorbed", "Closed")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	events = get_events(filters)
	return get_columns(), build_tree(events), None, None, get_summary(events)


def get_columns():
	return [
		{"fieldname": "label", "label": _("Award / Status / Change"), "fieldtype": "Data", "width": 300},
		{"fieldname": "change_event", "label": _("Change Event"), "fieldtype": "Link", "options": "Change Event", "width": 125},
		{"fieldname": "raised_on", "label": _("Raised On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "age_days", "label": _("Age (Days)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 130},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 120},
		{"fieldname": "rough_cost", "label": _("Rough Cost"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "rough_days", "label": _("Rough Days"), "fieldtype": "Int", "width": 95},
		{"fieldname": "count", "label": _("Events"), "fieldtype": "Int", "width": 75},
		{"fieldname": "variation_order", "label": _("Variation Order"), "fieldtype": "Link", "options": "Variation Order", "width": 125},
	]


def get_events(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("awarded_quotation"):
		conditions["awarded_quotation"] = filters.awarded_quotation
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("open_only"):
		conditions["status"] = ["in", list(OPEN)]
	return frappe.get_list(
		"Change Event",
		filters=conditions,
		fields=["name", "title", "awarded_quotation", "raised_on", "source", "wbs", "rough_cost", "rough_days", "status", "variation_order"],
		order_by="raised_on asc",
		limit_page_length=0,
	)


def build_tree(events):
	titles = {}
	awards = OrderedDict()
	for e in sorted(events, key=lambda e: e.awarded_quotation):
		awards.setdefault(e.awarded_quotation, []).append(e)
	if awards and frappe.has_permission("Awarded Quotation", "read"):
		titles = dict(frappe.get_list("Awarded Quotation", filters={"name": ["in", list(awards)]}, fields=["name", "title"], as_list=True))
	now = today()
	data = []
	for award, rows in awards.items():
		open_rows = [e for e in rows if e.status in OPEN]
		data.append({
			"id": award, "parent_id": None, "indent": 0, "is_group": 1,
			"label": f"{award} · {titles.get(award) or ''}".strip(" ·"),
			"rough_cost": sum(flt(e.rough_cost) for e in open_rows), "rough_days": sum(e.rough_days or 0 for e in open_rows),
			"count": len(rows), "note": _("open exposure"),
		})
		for status in STATUSES:
			group = [e for e in rows if e.status == status]
			if not group:
				continue
			gid = f"{award}::{status}"
			data.append({
				"id": gid, "parent_id": award, "indent": 1, "is_group": 1, "status": status, "is_open": status in OPEN,
				"label": _(status), "count": len(group),
				"rough_cost": sum(flt(e.rough_cost) for e in group), "rough_days": sum(e.rough_days or 0 for e in group),
			})
			for e in group:
				data.append({
					"id": e.name, "parent_id": gid, "indent": 2, "label": e.title, "change_event": e.name,
					"raised_on": e.raised_on, "age_days": date_diff(now, e.raised_on) if e.status in OPEN else None,
					"source": _(e.source), "wbs": e.wbs, "rough_cost": e.rough_cost, "rough_days": e.rough_days,
					"variation_order": e.variation_order, "status": e.status, "is_open": e.status in OPEN,
				})
	return data


def get_summary(events):
	open_rows = [e for e in events if e.status in OPEN]
	return [
		{"label": _("Open exposure"), "value": sum(flt(e.rough_cost) for e in open_rows), "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Days at risk"), "value": sum(e.rough_days or 0 for e in open_rows), "datatype": "Int", "indicator": "Orange"},
		{"label": _("Open events"), "value": len(open_rows), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Became variation orders"), "value": len([e for e in events if e.status == "Became VO"]), "datatype": "Int",
		 "indicator": "Green"},
	]
