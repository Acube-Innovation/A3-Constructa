# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Build the Masiha Services SARL demo, or one stage of it.

    bench --site <site> execute a3_constructa.demo.masiha.run.run
    bench --site <site> execute a3_constructa.demo.masiha.run.run --kwargs "{'stage': 'masters'}"

Idempotent: each stage creates what is missing and leaves what is there, so it
can be re-run after a failure without doubling anything up. The stages follow
the client's 21-step demonstration flow in order.
"""

import frappe

STAGES = [
	("setup", "a3_constructa.demo.masiha.setup.run"),  # step 1: company, people, controls
	("masters", "a3_constructa.demo.masiha.masters.run"),  # step 1: masters
	("planning", "a3_constructa.demo.masiha.planning.run"),  # steps 2-4
	("wbs", "a3_constructa.demo.masiha.wbs.run"),  # P-01A: node types, location, BOQ line, status cases
	("allowances", "a3_constructa.demo.masiha.allowances.run"),  # P-01B: allowance lines, allocations in every state
	("budget", "a3_constructa.demo.masiha.budget.run"),  # P-01C: revision reason, budget transfers in every state
	("ledger", "a3_constructa.demo.masiha.ledger.run"),  # P-01D: WBS and cost code on invoices, journals, claims, GL
	("approvals", "a3_constructa.demo.masiha.approvals.run"),  # P-09A: approval levels and budget check, every state
	("wbs_overview", "a3_constructa.demo.masiha.wbs_overview.run"),  # D-01: cases for the overview's checks
	("crm", "a3_constructa.demo.masiha.crm.run"),  # P-02A: leads and opportunities, tenders due this week
	("tender", "a3_constructa.demo.masiha.tender.run"),  # P-02B: tender BOQs imported from the clients' bills
	("estimates", "a3_constructa.demo.masiha.estimates.run"),  # P-02C: rate build-up on the hospital tender
	("pricing", "a3_constructa.demo.masiha.pricing.run"),  # P-02D: preliminaries, markups, contingency
	("quotations", "a3_constructa.demo.masiha.quotations.run"),  # P-02E: revisions, margin approval, win / loss
	("crm_overview", "a3_constructa.demo.masiha.crm_overview.run"),  # D-02: a case for every overview check
	("change_events", "a3_constructa.demo.masiha.change_events.run"),  # P-03A: change events in every status
	("variations", "a3_constructa.demo.masiha.variations.run"),  # P-03B: variation orders in every status, budget moves
	("handover", "a3_constructa.demo.masiha.handover.run"),  # P-03C: the hospital is won and handed over in one step
	("contracts_overview", "a3_constructa.demo.masiha.contracts_overview.run"),  # D-03: a case for every overview check
	("contract_terms", "a3_constructa.demo.masiha.contract_terms.run"),  # P-04A: terms on awards and the hospital's order
	("milestone_billing", "a3_constructa.demo.masiha.milestone_billing.run"),  # P-04B: the hospital billed by milestones
	("client_ipc", "a3_constructa.demo.masiha.client_ipc.run"),  # P-04C: advance, IPCs, retention on the Administrative Centre
	("final_account", "a3_constructa.demo.masiha.final_account.run"),  # P-04D: a small school job closed out to its final account
	("subcontract_compliance", "a3_constructa.demo.masiha.subcontract_compliance.run"),  # P-09B: back-charges, the compliance gate
	("billing_overview", "a3_constructa.demo.masiha.billing_overview.run"),  # D-04: a case for every Sales & Billing check
	("crews", "a3_constructa.demo.masiha.crews.run"),  # P-07A: site workers, wages and crews in every state
	("equipment", "a3_constructa.demo.masiha.equipment.run"),  # P-08A: plant logs, owned at an internal rate and hired
	("operations", "a3_constructa.demo.masiha.operations.run"),  # W-06: the jobs' programmes as tasks
	("requests", "a3_constructa.demo.masiha.requests.run"),  # steps 5-7
	("purchasing", "a3_constructa.demo.masiha.purchasing.run"),  # steps 8, 14, 15, 19
	("logistics", "a3_constructa.demo.masiha.logistics.run"),  # steps 9-13
	("stores", "a3_constructa.demo.masiha.stores.run"),  # steps 16-18
	("assets", "a3_constructa.demo.masiha.assets.run"),  # step 19
	("finance", "a3_constructa.demo.masiha.finance.run"),  # step 20
	("closure", "a3_constructa.demo.masiha.closure.run"),  # step 21
	("timeline", "a3_constructa.demo.masiha.timeline.run"),  # dates everything on the story calendar
]


def run(stage: str | None = None):
	frappe.flags.mute_emails = True
	for name, method in STAGES:
		if stage and stage != name:
			continue
		print(f"\n=== {name} ===")
		try:
			frappe.get_attr(method)()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			print(f"  !! {name} failed")
			raise
	print("\nMasiha demo ready.")
