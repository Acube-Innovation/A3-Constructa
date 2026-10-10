# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Bid Decisions - catalogue 2.2.

Every opportunity with its bid / no-bid score: the six criteria as scored, the
total out of 100 against the threshold of its day, what the score suggested,
and what was decided, by whom and when, with the reason for a No-go. A decision
that went against the score is marked, so management can see where judgement
overrode the numbers. Opportunities not yet scored are listed too while they
are still open, so nothing is bid by default.

Filters: company, stage of the decision, sector, and tender due date.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.overrides.opportunity import AWAITING, CRITERIA, GO, NO_GO, SCORING, threshold

STAGES = ("Not scored", "Scoring", "Awaiting decision", "Go", "No-go")
STAGE_OF = {SCORING: "Scoring", AWAITING: "Awaiting decision", GO: "Go", NO_GO: "No-go"}
OPEN = ("Open", "Replied", "Quotation")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_data(filters)
	return get_columns(), rows, None, get_chart(rows), get_summary(rows)


def get_data(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("sector"):
		conditions["sector"] = filters.sector
	if filters.get("from_date") and filters.get("to_date"):
		conditions["tender_due_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		conditions["tender_due_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		conditions["tender_due_date"] = ["<=", filters.to_date]
	opportunities = frappe.get_list(
		"Opportunity",
		filters=conditions,
		fields=["name", "title", "party_name", "customer_name", "status", "sector", "estimated_value", "opportunity_amount",
		        "tender_due_date", "total_score", "bid_threshold", "suggested_decision", "bid_decision", "bid_workflow_state",
		        "decided_by", "decided_on", "no_go_reason", "no_go_note"],
		order_by="tender_due_date asc, name asc",
		limit_page_length=0,
	)
	scores = {}
	if opportunities:
		for row in frappe.get_all("Bid Score", filters={"parenttype": "Opportunity", "parent": ["in", [o.name for o in opportunities]]},
		                          fields=["parent", "criterion", "score"]):
			scores.setdefault(row.parent, {})[row.criterion] = row.score
	rows = []
	for o in opportunities:
		stage = STAGE_OF.get(o.bid_workflow_state) if o.name in scores else None
		stage = stage or ("Not scored" if o.name not in scores else "Scoring")
		if stage == "Not scored" and o.status not in OPEN:
			continue  # closed, lost or converted before bid scoring existed: nothing to decide
		if filters.get("stage") and filters.stage != stage:
			continue
		row = {
			"opportunity": o.name,
			"title": o.title,
			"client": o.customer_name or o.party_name,
			"sector": o.sector,
			"value": flt(o.estimated_value) or flt(o.opportunity_amount),
			"tender_due_date": o.tender_due_date,
			"total_score": o.total_score if o.name in scores else None,
			"threshold": o.bid_threshold if o.name in scores else None,
			"suggested": _(o.suggested_decision) if o.suggested_decision else None,
			"stage": _(stage),
			"stage_key": stage,
			"against_score": int(stage in ("Go", "No-go") and bool(o.suggested_decision) and o.suggested_decision != stage),
			"decided_by": frappe.utils.get_fullname(o.decided_by) if o.decided_by else None,
			"decided_on": o.decided_on,
			"no_go_reason": _(o.no_go_reason) if o.no_go_reason else None,
			"note": o.no_go_note,
		}
		for criterion in CRITERIA:
			row[key(criterion)] = scores.get(o.name, {}).get(criterion)
		rows.append(row)
	return rows


def key(criterion):
	return "c_" + criterion.lower().replace(" ", "_")


def get_columns():
	cols = [
		{"fieldname": "opportunity", "label": _("Opportunity"), "fieldtype": "Link", "options": "Opportunity", "width": 150},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 220},
		{"fieldname": "client", "label": _("Client"), "fieldtype": "Data", "width": 170},
		{"fieldname": "sector", "label": _("Sector"), "fieldtype": "Data", "width": 105},
		{"fieldname": "value", "label": _("Estimated Value"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "tender_due_date", "label": _("Tender Due"), "fieldtype": "Date", "width": 100},
	]
	cols += [{"fieldname": key(c), "label": _(c), "fieldtype": "Int", "width": 85} for c in CRITERIA]
	cols += [
		{"fieldname": "total_score", "label": _("Score"), "fieldtype": "Float", "precision": 1, "width": 75},
		{"fieldname": "threshold", "label": _("Threshold"), "fieldtype": "Float", "precision": 1, "width": 90},
		{"fieldname": "suggested", "label": _("Score Suggests"), "fieldtype": "Data", "width": 110},
		{"fieldname": "stage", "label": _("Decision"), "fieldtype": "Data", "width": 135},
		{"fieldname": "against_score", "label": _("Against the Score"), "fieldtype": "Check", "width": 120},
		{"fieldname": "decided_by", "label": _("Decided By"), "fieldtype": "Data", "width": 140},
		{"fieldname": "decided_on", "label": _("Decided On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "no_go_reason", "label": _("No-go Reason"), "fieldtype": "Data", "width": 120},
		{"fieldname": "note", "label": _("Decision Note"), "fieldtype": "Data", "width": 260},
	]
	return cols


def get_chart(rows):
	"""Each scored opportunity's score, with the current threshold as a line across."""
	scored = [r for r in rows if r["total_score"] is not None]
	if not scored:
		return None
	line = threshold()
	return {
		"data": {
			"labels": [r["title"] if len(r["title"] or "") <= 24 else r["title"][:23] + "…" for r in scored],
			"datasets": [{"name": _("Bid score"), "values": [flt(r["total_score"]) for r in scored]}],
			"yMarkers": [{"label": _("Threshold {0}").format(f"{line:g}"), "value": line}],
		},
		"type": "bar",
		"colors": ["#3a6ea5"],
		"axisOptions": {"xIsSeries": 0},
	}


def get_summary(rows):
	def count(stage):
		return [r for r in rows if r["stage_key"] == stage]
	go, no_go = count("Go"), count("No-go")
	return [
		{"label": _("Go"), "value": len(go), "datatype": "Int", "indicator": "Green"},
		{"label": _("Value bid (Go)"), "value": sum(r["value"] for r in go), "datatype": "Currency", "indicator": "Green"},
		{"label": _("No-go"), "value": len(no_go), "datatype": "Int", "indicator": "Red"},
		{"label": _("Value declined"), "value": sum(r["value"] for r in no_go), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Awaiting decision"), "value": len(count("Awaiting decision")), "datatype": "Int", "indicator": "Orange"},
		{"label": _("Open, not scored"), "value": len(count("Not scored")), "datatype": "Int", "indicator": "Grey"},
		{"label": _("Against the score"), "value": sum(r["against_score"] for r in rows), "datatype": "Int", "indicator": "Blue"},
	]
