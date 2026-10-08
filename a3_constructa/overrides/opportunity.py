# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Bid / no-bid on an opportunity - catalogue 2.2.

Before money is spent on a tender, the opportunity is scored on six criteria,
each 1 (poor) to 5 (excellent) and weighted so the weights add up to 100%. A
criterion's points are weight × score ÷ 5, so the bid score is out of 100. At
or above the threshold in A3 Constructa Settings (60 unless changed) the score
suggests Go; below it, No-go.

The "Bid Decision" workflow takes it from there: sales sends the scored
opportunity for a decision, and a sales manager other than its owner confirms
Go or No-go (or sends it back). A No-go needs a reason, which the No-bid
Reasons view of Win Loss Analysis reads, and closes the opportunity: no tender
BOQ or quotation is made for it. A decided opportunity keeps its scores until
a manager reopens it.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, today

CRITERIA = ("Capacity", "Margin", "Risk", "Payment terms", "Client history", "Strategic fit")
# Starting weights for "Score the bid"; each opportunity may weigh them its own way.
DEFAULT_WEIGHTS = {"Capacity": 20, "Margin": 20, "Risk": 20, "Payment terms": 15, "Client history": 10, "Strategic fit": 15}
DEFAULT_THRESHOLD = 60.0

SCORING, AWAITING, GO, NO_GO = "Scoring", "Awaiting Bid Decision", "Go", "No-go"
DECISION = {SCORING: "Pending", AWAITING: "Pending", GO: "Go", NO_GO: "No-go"}


def threshold() -> float:
	"""The setting, or 60 while it has never been saved (0 is a real choice: always suggest Go)."""
	value = frappe.db.get_value("Singles", {"doctype": "A3 Constructa Settings", "field": "bid_threshold_score"}, "value", order_by=None)
	return flt(value) if value is not None else DEFAULT_THRESHOLD


def validate(doc, method=None):
	state = doc.get("bid_workflow_state")
	before = doc.get_doc_before_save()
	decided_before = before and before.get("bid_workflow_state") in (GO, NO_GO)
	if decided_before and state in (GO, NO_GO) and scores_changed(doc, before):
		frappe.throw(_("The bid decision is made. A sales manager reopens it before the scores change."), title=_("Bid already decided"))
	score(doc)
	if decided_before and state in (GO, NO_GO) and before.get("bid_threshold") is not None:
		# A decision is judged against the threshold of its day.
		doc.bid_threshold = before.bid_threshold
		doc.suggested_decision = GO if flt(doc.total_score) >= flt(doc.bid_threshold) else NO_GO
	record_decision(doc, before)


def score(doc):
	rows = doc.get("bid_scores") or []
	seen = set()
	for row in rows:
		if row.criterion in seen:
			frappe.throw(_("Row {0}: {1} is scored twice.").format(row.idx, _(row.criterion)), title=_("Bid score"))
		seen.add(row.criterion)
		if not 1 <= cint(row.score) <= 5:
			frappe.throw(_("Row {0}: score {1} from 1 (poor) to 5 (excellent).").format(row.idx, _(row.criterion)), title=_("Bid score"))
		if flt(row.weight) <= 0:
			frappe.throw(_("Row {0}: give {1} a weight above 0%, or remove the row.").format(row.idx, _(row.criterion)), title=_("Bid score"))
		row.weighted = flt(flt(row.weight) * cint(row.score) / 5, 2)
	if rows:
		weights = sum(flt(row.weight) for row in rows)
		if abs(weights - 100) > 0.01:
			frappe.throw(_("The weights add up to {0}%. They must add up to 100%.").format(f"{flt(weights, 2):g}"), title=_("Bid score"))
	doc.total_score = flt(sum(flt(row.weighted) for row in rows), 1) if rows else None
	doc.bid_threshold = threshold() if rows else None
	if rows:
		doc.suggested_decision = GO if flt(doc.total_score) >= flt(doc.bid_threshold) else NO_GO
	else:
		doc.suggested_decision = None


def record_decision(doc, before):
	state = doc.get("bid_workflow_state")
	if not state:
		return
	doc.bid_decision = DECISION.get(state, "Pending")
	changed = not before or before.get("bid_workflow_state") != state
	if state == NO_GO and not doc.no_go_reason:
		frappe.throw(_("Choose the No-go Reason before confirming No-go."), title=_("Reason needed"))
	if not changed:
		return
	if state in (GO, NO_GO):
		doc.decided_by, doc.decided_on = frappe.session.user, today()
		if state == NO_GO and doc.status not in ("Lost", "Converted"):
			doc.status = "Closed"
	else:
		doc.decided_by = doc.decided_on = None
		if before and before.get("bid_workflow_state") == NO_GO:
			doc.no_go_reason = None
			if doc.status == "Closed":
				doc.status = "Open"


def scores_changed(doc, before):
	key = lambda d: sorted((r.criterion, flt(r.weight), cint(r.score)) for r in (d.get("bid_scores") or []))
	return key(doc) != key(before)


def refuse_if_no_go(opportunity):
	"""No tender BOQ or quotation for an opportunity the company decided not to bid."""
	if opportunity and frappe.db.get_value("Opportunity", opportunity, "bid_decision") == "No-go":
		frappe.throw(_("{0} was decided No-go: there is no bid to prepare. A sales manager can reopen the decision.").format(opportunity),
		             title=_("Not bidding"))


@frappe.whitelist()
def default_scores() -> list[dict]:
	"""The six criteria with their starting weights, for "Score the bid"."""
	return [{"criterion": c, "weight": DEFAULT_WEIGHTS[c]} for c in CRITERIA]
