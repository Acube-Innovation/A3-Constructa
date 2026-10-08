# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Tender Register - catalogue 2.3.

Each tender (an open opportunity) with what the client issued and what is still
being asked: a row per tender, under it its documents revision by revision
(superseded ones marked), then its clarifications, oldest first, with how long
an open one has waited. Answered queries that changed the price are kept in
view; the rest of the answered ones show when asked for.

Filters: company, one tender, closed tenders too, answered queries too.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, today

OPEN = ("Open", "Replied", "Quotation")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows, totals = get_data(filters)
	return get_columns(), rows, None, None, get_summary(totals)


def get_data(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("opportunity"):
		conditions["name"] = filters.opportunity
	elif not filters.get("include_closed"):
		conditions["status"] = ["in", OPEN]
	opportunities = frappe.get_list("Opportunity", filters=conditions,
	                                fields=["name", "title", "status", "tender_due_date", "bid_decision", "bid_workflow_state"],
	                                order_by="tender_due_date asc, name asc", limit_page_length=0)
	names = [o.name for o in opportunities]
	documents, queries = {}, {}
	if names:
		for d in frappe.get_all("Tender Document", filters={"parenttype": "Opportunity", "parent": ["in", names]},
		                        fields=["parent", "document_type", "title", "revision", "received_on", "superseded", "attachment"],
		                        order_by="document_type asc, title asc, received_on asc, idx asc"):
			documents.setdefault(d.parent, []).append(d)
		if frappe.has_permission("Tender Clarification", "read"):
			for q in frappe.get_list("Tender Clarification", filters={"opportunity": ["in", names]},
			                         fields=["name", "opportunity", "query_no", "question", "raised_on", "status", "answered_on",
			                                 "price_impact", "impact_note", "answer"],
			                         order_by="query_no asc", limit_page_length=0):
				queries.setdefault(q.opportunity, []).append(q)
	now = getdate(today())
	rows = []
	totals = frappe._dict(tenders=0, documents=0, superseded=0, open=0, oldest=0, impact=0)
	for o in opportunities:
		docs = documents.get(o.name, [])
		qs = queries.get(o.name, [])
		if not docs and not qs and not filters.get("opportunity"):
			continue
		open_qs = [q for q in qs if q.status == "Open"]
		totals.tenders += 1
		totals.documents += len(docs)
		totals.superseded += sum(d.superseded for d in docs)
		totals.open += len(open_qs)
		totals.impact += sum(q.price_impact for q in qs)
		rows.append({"label": o.title, "kind": _("Tender"), "reference": o.name, "doctype": "Opportunity", "indent": 0,
		             "date": o.tender_due_date, "status": bid_status(o),
		             "documents": len([d for d in docs if not d.superseded]), "open_queries": len(open_qs),
		             "days": date_diff(o.tender_due_date, now) if o.tender_due_date else None})
		for d in docs:
			rows.append({"label": d.title, "kind": _(d.document_type), "reference": d.attachment, "indent": 1, "revision": d.revision,
			             "date": d.received_on, "status": _("Superseded") if d.superseded else _("Current")})
		for q in qs:
			if q.status == "Answered" and not q.price_impact and not filters.get("include_answered"):
				continue
			waited = date_diff(now, q.raised_on) if q.status == "Open" else date_diff(q.answered_on, q.raised_on)
			if q.status == "Open":
				totals.oldest = max(totals.oldest, waited)
			rows.append({"label": q.question, "kind": _("Clarification {0}").format(q.query_no), "reference": q.name,
			             "doctype": "Tender Clarification", "indent": 1, "date": q.raised_on,
			             "status": _("Open") if q.status == "Open" else _("Answered, price impact") if q.price_impact else _("Answered"),
			             "days": waited, "price_impact": q.price_impact,
			             "detail": q.impact_note if q.price_impact else (q.answer or "")[:140]})
	return rows, totals


def bid_status(o):
	"""The tender's bid stage where it has one (P-02F), else the opportunity's status."""
	if o.bid_decision in ("Go", "No-go"):
		return _("Bid: {0}").format(_(o.bid_decision))
	if o.bid_workflow_state == "Awaiting Bid Decision":
		return _("Bid decision pending")
	return _(o.status)


def get_columns():
	return [
		{"fieldname": "label", "label": _("Tender / Document / Question"), "fieldtype": "Data", "width": 330},
		{"fieldname": "kind", "label": _("Type"), "fieldtype": "Data", "width": 150},
		{"fieldname": "revision", "label": _("Revision"), "fieldtype": "Data", "width": 80},
		{"fieldname": "date", "label": _("Due / Received / Raised"), "fieldtype": "Date", "width": 150},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "days", "label": _("Days"), "fieldtype": "Int", "width": 70},
		{"fieldname": "documents", "label": _("Current Documents"), "fieldtype": "Int", "width": 130},
		{"fieldname": "open_queries", "label": _("Open Queries"), "fieldtype": "Int", "width": 105},
		{"fieldname": "price_impact", "label": _("Price Impact"), "fieldtype": "Check", "width": 95},
		{"fieldname": "detail", "label": _("Impact / Answer"), "fieldtype": "Data", "width": 280},
		{"fieldname": "reference", "label": _("Reference"), "fieldtype": "Data", "width": 170},
		{"fieldname": "doctype", "label": _("Doctype"), "fieldtype": "Data", "hidden": 1},
	]


def get_summary(t):
	return [
		{"label": _("Tenders"), "value": t.tenders, "datatype": "Int", "indicator": "Blue"},
		{"label": _("Documents received"), "value": t.documents, "datatype": "Int", "indicator": "Blue"},
		{"label": _("Superseded revisions"), "value": t.superseded, "datatype": "Int", "indicator": "Grey"},
		{"label": _("Open queries"), "value": t.open, "datatype": "Int", "indicator": "Orange" if t.open else "Green"},
		{"label": _("Oldest open (days)"), "value": t.oldest, "datatype": "Int", "indicator": "Orange" if t.oldest > 7 else "Grey"},
		{"label": _("Answers with a price impact"), "value": t.impact, "datatype": "Int", "indicator": "Red" if t.impact else "Grey"},
	]
