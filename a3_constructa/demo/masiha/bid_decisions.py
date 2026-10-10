# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02F: bid / no-bid scores and decisions on the pipeline.

Bernadette Mbo (business development) scores each tender; Albert Nzuzi (MD)
confirms the decision, as the owner of an opportunity may not confirm her own.
Scores are 1 (poor) to 5 (excellent) on capacity, margin, risk, payment terms,
client history and strategic fit, weighted 20/20/20/15/10/15; the threshold is 60.

- Hospital extension (79), annex B (82), university library (71) and the
  Assembly roof (64, later lost on price): Go.
- Wangata solar retrofit: 56, below the threshold, but the MD confirmed Go for
  the foothold in health-sector solar work. It shows as against the score.
- Wangata water tower: 49, sent for decision and waiting for the MD.
- Gemena airport terminal (new): 40. No-go on payment terms: the airport
  authority still owes contractors on its runway works. The opportunity closes.
- The Bikoro road, the stadium and the two direct awards are not scored.
"""

import frappe
from frappe.model.workflow import apply_workflow

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, day, insert, log, user

ORDER = ("Capacity", "Margin", "Risk", "Payment terms", "Client history", "Strategic fit")
WEIGHTS = (20, 20, 20, 15, 10, 15)
GEMENA = "Gemena airport: passenger terminal"

# title, scores in ORDER, outcome (Go / No-go / Awaiting), decided days ago, reason, note
BIDS = [
	("Hospital extension: maternity and theatre block", (4, 4, 3, 4, 4, 5), "Go", -50, None,
	 "Our health-sector reference job; the provincial health budget is ring-fenced."),
	("Administrative Centre: annex B offices", (4, 4, 4, 4, 5, 4), "Go", -30, None, "Same client, same site: our crews are already there."),
	("University library block", (4, 3, 4, 3, 3, 4), "Go", -12, None, None),
	("Provincial Assembly: roof replacement", (3, 3, 4, 3, 3, 3), "Go", -75, None, None),
	("Wangata health centre: solar power retrofit", (2, 2, 3, 3, 2, 5), "Go", -3, None,
	 "Below the threshold, but small and our first solar job in health: worth it to bid the hospital's energy package next."),
	("Water tower, Wangata commune", (2, 3, 2, 3, 3, 2), "Awaiting", None, None, None),
	(GEMENA, (1, 3, 2, 1, 2, 3), "No-go", -6, "Payment terms",
	 "The airport authority still owes contractors on the 2024 runway works, and an 18-month job would tie up both site teams."),
]
NOTES = {
	"Capacity": {1: "Both site teams committed until mid-2027", 2: "Steel fixers busy on the hospital in Nov-Dec"},
	"Payment terms": {1: "Arrears on earlier works; no advance offered"},
}


def run():
	gemena = gemena_opportunity()
	done = []
	for title, scores, outcome, when, reason, note in BIDS:
		name = frappe.db.get_value("Opportunity", {"title": title, "company": COMPANY}, "name")
		if not name:
			continue
		if frappe.db.exists("Bid Score", {"parenttype": "Opportunity", "parent": name}):
			continue  # already scored: the stage runs once per opportunity
		done.append(decide(name, scores, outcome, when, reason, note))
	log("Bid decisions: " + ("; ".join(done) if done else "already in place") + (f" (new: {gemena})" if gemena else ""))


def gemena_opportunity():
	if frappe.db.exists("Opportunity", {"title": GEMENA}):
		return None
	with as_user("sales"):
		lead = insert({"doctype": "Lead", "first_name": "Jean-Claude", "last_name": "Mokili", "company_name": "Régie des Voies Aériennes, Gemena",
		               "company": COMPANY, "sector": "Infrastructure", "enquiry_channel": "Public tender", "estimated_value": 4_800_000,
		               "tender_due_date": day(24)})
		o = insert({"doctype": "Opportunity", "opportunity_from": "Lead", "party_name": lead.name, "company": COMPANY, "title": GEMENA,
		            "currency": "USD", "opportunity_amount": 4_800_000, "probability": 15, "sector": "Infrastructure",
		            "enquiry_channel": "Public tender", "estimated_value": 4_800_000, "tender_due_date": day(24),
		            "expected_award_date": day(70), "expected_closing": day(70), "estimated_duration_months": 18,
		            "opportunity_owner": user("sales"), "transaction_date": day(-14)})
	frappe.db.set_value("Opportunity", o.name, "creation", at(-14, 10), update_modified=False)
	frappe.db.set_value("Lead", lead.name, "creation", at(-15, 9), update_modified=False)
	return o.name


def decide(name, scores, outcome, when, reason, note):
	with as_user("sales"):
		o = frappe.get_doc("Opportunity", name)
		o.set("bid_scores", [])
		for criterion, weight, score in zip(ORDER, WEIGHTS, scores):
			o.append("bid_scores", {"criterion": criterion, "weight": weight, "score": score,
			                        "note": NOTES.get(criterion, {}).get(score)})
		o.flags.ignore_permissions = True
		o.save()
		o = apply_workflow(o, "Send for Decision")
	if outcome != "Awaiting":
		with as_user("md"):
			o = frappe.get_doc("Opportunity", name)
			if reason:
				o.no_go_reason = reason
			if note:
				o.no_go_note = note
			o.flags.ignore_permissions = True
			o.save()
			o = apply_workflow(o, "Confirm Go" if outcome == "Go" else "Confirm No-go")
		frappe.db.set_value("Opportunity", name, "decided_on", day(when), update_modified=False)
	return f"{name} {o.total_score:g} → {outcome}"
