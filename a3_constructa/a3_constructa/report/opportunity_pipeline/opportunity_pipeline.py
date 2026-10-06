# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Opportunity Pipeline - catalogue 2.1.

The tenders being chased, grouped by sales stage or by the month the client is
expected to award them: value, the standard probability, and weighted value
(value x probability). The chart shows weighted value by expected award month.

Value is the opportunity amount in company currency, or the estimated value
where no amount has been priced yet. "Due soon" keeps only tenders due in the
next 7 days that have no quotation yet.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import add_days, flt, formatdate, getdate, today

OPEN_STATUSES = ("Open", "Replied", "Quotation")
DUE_SOON_DAYS = 7


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_opportunities(filters)
	group_by = filters.get("group_by") or "Sales Stage"
	return get_columns(), build_tree(rows, group_by), None, get_chart(rows, filters)


def get_columns():
	return [
		{"fieldname": "label", "label": _("Stage / Opportunity"), "fieldtype": "Data", "width": 230},
		{"fieldname": "opportunity", "label": _("Opportunity"), "fieldtype": "Link", "options": "Opportunity", "width": 140},
		{"fieldname": "client", "label": _("Client"), "fieldtype": "Data", "width": 200},
		{"fieldname": "sector", "label": _("Sector"), "fieldtype": "Data", "width": 110},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "probability", "label": _("Probability %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "weighted", "label": _("Weighted Value"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "expected_award_date", "label": _("Expected Award"), "fieldtype": "Date", "width": 115},
		{"fieldname": "tender_due_date", "label": _("Tender Due"), "fieldtype": "Date", "width": 105},
		{"fieldname": "quoted", "label": _("Quoted"), "fieldtype": "Data", "width": 75},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "owner_name", "label": _("Owner"), "fieldtype": "Data", "width": 130},
	]


def get_opportunities(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("sector"):
		conditions["sector"] = filters.sector
	if filters.get("owner"):
		conditions["opportunity_owner"] = filters.owner
	conditions["status"] = filters.status if filters.get("status") else ["in", list(OPEN_STATUSES)]
	if filters.get("due_soon"):
		conditions["tender_due_date"] = ["between", [today(), add_days(today(), DUE_SOON_DAYS)]]

	rows = frappe.get_list(
		"Opportunity",
		filters=conditions,
		fields=["name", "title", "customer_name", "party_name", "opportunity_from", "sector", "sales_stage", "probability",
		        "base_opportunity_amount", "estimated_value", "conversion_rate", "expected_award_date", "expected_closing",
		        "tender_due_date", "status", "opportunity_owner"],
		order_by="expected_award_date, name",
		limit_page_length=0,
	)
	quoted = set(frappe.get_all("Quotation", filters={"opportunity": ["in", [r.name for r in rows] or [""]], "docstatus": ["<", 2]},
	                            pluck="opportunity"))
	for r in rows:
		r.value = flt(r.base_opportunity_amount) or flt(r.estimated_value) * (flt(r.conversion_rate) or 1)
		r.weighted = r.value * flt(r.probability) / 100
		r.award = r.expected_award_date or r.expected_closing
		r.quoted = r.name in quoted
	if filters.get("due_soon"):
		rows = [r for r in rows if not r.quoted]
	return rows


def build_tree(rows, group_by):
	groups = OrderedDict()
	if group_by == "Award Month":
		for r in sorted(rows, key=lambda r: (r.award is None, getdate(r.award) if r.award else None)):
			key = getdate(r.award).strftime("%Y-%m") if r.award else ""
			label = formatdate(r.award, "MMMM yyyy") if r.award else _("No award date")
			groups.setdefault(key, {"label": label, "rows": []})["rows"].append(r)
	else:
		order = frappe.get_all("Sales Stage", pluck="name", order_by="creation")
		for stage in order + [None]:
			for r in rows:
				if (r.sales_stage or None) == stage:
					groups.setdefault(stage or "", {"label": _(stage) if stage else _("No sales stage"), "rows": []})["rows"].append(r)

	owners = {u: frappe.utils.get_fullname(u) for u in {r.opportunity_owner for r in rows if r.opportunity_owner}}
	data = []
	for key, group in groups.items():
		value = sum(r.value for r in group["rows"])
		weighted = sum(r.weighted for r in group["rows"])
		group_id = f"group::{key}"
		data.append({
			"id": group_id, "parent_id": None, "indent": 0, "is_group": 1,
			"label": f"{group['label']} ({len(group['rows'])})",
			"value": value, "weighted": weighted,
			"probability": weighted / value * 100 if value else None,
		})
		for r in group["rows"]:
			data.append({
				"id": r.name, "parent_id": group_id, "indent": 1,
				"label": r.title or r.customer_name or r.party_name, "opportunity": r.name,
				"client": r.customer_name or r.party_name, "sector": _(r.sector) if r.sector else None,
				"value": r.value, "probability": flt(r.probability), "weighted": r.weighted,
				"expected_award_date": r.award, "tender_due_date": r.tender_due_date,
				"quoted": _("Yes") if r.quoted else _("No"), "status": _(r.status),
				"owner_name": owners.get(r.opportunity_owner),
				"due_soon": int(bool(r.tender_due_date and not r.quoted
				                     and getdate(today()) <= getdate(r.tender_due_date) <= getdate(add_days(today(), DUE_SOON_DAYS)))),
			})
	return data


def get_chart(rows, filters):
	months = OrderedDict()
	for r in sorted(rows, key=lambda r: (r.award is None, getdate(r.award) if r.award else None)):
		if not r.award:
			continue
		key = getdate(r.award).strftime("%Y-%m")
		months.setdefault(key, {"label": formatdate(r.award, "MMM yyyy"), "weighted": 0.0, "value": 0.0})
		months[key]["weighted"] += r.weighted
		months[key]["value"] += r.value
	if not months:
		return None
	return {
		"data": {
			"labels": [m["label"] for m in months.values()],
			"datasets": [
				{"name": _("Weighted value"), "values": [round(m["weighted"], 2) for m in months.values()]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
		"colors": ["#2f6b3d"],
		"title": _("Weighted value by expected award month"),
	}
