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
