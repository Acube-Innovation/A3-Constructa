# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-04D: a small job carried to its final account.

Classroom block refurbishment at Bikoro primary school, for the Fondation Lisanga
pour l'Education: a minor-works contract of $51,620, 5% retention, a two-month
defects period, billed by interim certificates.

- April: awarded; one approved variation adds 60 m² of roof sheeting over the veranda.
- IPC 1 (to early June) and IPC 2 (the final measurement, July) certified, invoiced
  and paid. The engineer cut the plaster claim from 840 to 790 m².
- Practical completion on 1 August; the first half of the retention released and paid.
- The final account: the work remeasured at $53,034 (below contract plus variation,
  $53,480, as the plaster came in under the bill), two agreed adjustments
  (prolongation +$2,400, broken glass contra-charge -$380) and one claim still
  disputed (rock at the ramp, $1,650: listed, not counted). Agreed by the managing
  director; the final invoice for the $2,020 balance is out with the client.
- The defects period ended on 1 October, so the remaining retention ($1,325.85) is
  ready for "Release remaining retention", left for the tester to press.
"""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

from a3_constructa.demo.masiha.common import COMPANY, acc, as_user, at, comment, day, log, user

TITLE = "Bikoro primary school: classroom block refurbishment"
CLIENT = "Fondation Lisanga pour l'Education"
PROJECT_NAME = "Bikoro primary school refurbishment"
ROOT = "BKS-W"
# (component, qty, uom, rate)
COMPONENTS = [
	("Demolition and making good", 1, "Lump Sum", 6_800),
	("Roof structure and sheeting", 520, "Square Meter", 31),
	("Plaster and paint, walls and ceilings", 1_450, "Square Meter", 6.40),
	("Floor screed and ceramic tiles", 380, "Square Meter", 29),
	("Doors and windows", 1, "Lump Sum", 8_400),
]
# Cumulative quantities by the start of each component's name: (claimed this period, certified this period)
IPC_1 = {"Demolition": 1, "Roof": 400, "Plaster": 600, "Doors": 0.4}
IPC_2 = {"Roof": 178, "Plaster": (840, 790), "Floor": 380, "Doors": 0.6}
ADJUSTMENTS = [
	("Prolongation: two weeks of rain stoppage in May, agreed with the engineer", 2_400, 1),
	("Contra-charge: client-supplied window glass broken on site", -380, 1),
	("Claim: rock met in the foundation excavation for the access ramp (disputed)", 1_650, 0),
]


def run():
	if frappe.db.exists("Awarded Quotation", {"title": TITLE}):
		log("final account job already present")
		return
	customer = ensure_customer()
	award, project = award_and_project(customer)
	vo = variation(award)
	from a3_constructa.a3_constructa.doctype.client_ipc.client_ipc import get_contract_lines

	with as_user("qs"):
		lines = get_contract_lines(award)
	ipc1, si1 = certificate(award, lines, day(-170), day(-125), IPC_1, sent=-122, certified=-118, invoiced=-117)
	ipc2, si2 = certificate(award, lines, day(-124), day(-76), IPC_2, sent=-74, certified=-68, invoiced=-67)
	frappe.db.set_value("Awarded Quotation", award, {"status": "Completed", "practical_completion_date": day(-66)})
	frappe.db.set_value("Project", project, {"status": "Completed", "actual_end_date": day(-66), "percent_complete": 100})
	with as_user("finance"):
		from a3_constructa.api.client_billing import release_retention

		r1 = submit_on(release_retention(award, 1), -64, due=-34)
	receive(si1, -90, "LIS-TRF-2026-041")
	receive(si2, -40, "LIS-TRF-2026-077")
	receive(r1, -34, "LIS-TRF-2026-078")
	fa, final = final_account(award)
	log(f"{award} completed ({project}, {vo}); {ipc1}/{si1} and {ipc2}/{si2} paid; first retention half {r1} paid; "
	    f"{fa} agreed, final invoice {final} with the client; remaining retention ready to release")


def ensure_customer():
	if not frappe.db.exists("Customer", CLIENT):
		frappe.get_doc({"doctype": "Customer", "customer_name": CLIENT, "customer_type": "Company", "customer_group": "Non Profit",
		                "territory": "All Territories", "default_currency": "USD"}).insert(ignore_permissions=True)
	return CLIENT


def award_and_project(customer):
	with as_user("md"):
		a = frappe.get_doc({"doctype": "Awarded Quotation", "title": TITLE, "customer": customer, "company": COMPANY, "currency": "USD",
		                    "award_date": day(-180), "award_reference": "FLE/BKS/2026/02", "status": "Awarded", "start_date": day(-170),
		                    "end_date": day(-80), "retention_percent": 5, "retention_cap_percent": 5, "advance_percent": 0,
		                    "defects_liability_months": 2, "contract_type": "Re-measured", "billing_basis": "Progress claims",
		                    "scope": "Refurbishment of the six-classroom block: new roof, plaster and paint, floors, doors and windows. Minor-works contract.",
		                    "components": [{"component": c, "qty": q, "uom": u, "rate": r} for c, q, u, r in COMPONENTS]})
		a.flags.ignore_permissions = True
		a.insert()
	with as_user("pm"):
		p = frappe.get_doc({"doctype": "Project", "project_name": PROJECT_NAME, "company": COMPANY, "customer": customer,
		                    "expected_start_date": day(-170), "expected_end_date": day(-80), "status": "Open",
		                    "cost_center": frappe.get_cached_value("Company", COMPANY, "cost_center"),
		                    "notes": f"Handed over from award {a.name}."})
		p.flags.ignore_permissions = True
		p.insert()
		w = frappe.get_doc({"doctype": "WBS", "wbs_code": ROOT, "wbs_name": "Classroom block refurbishment", "project": p.name,
		                    "node_type": "WBS", "status": "Active", "is_group": 0})
		w.flags.ignore_permissions = True
		w.insert()
	frappe.db.set_value("Awarded Quotation", a.name, {"project": p.name, "status": "In Progress"})
	comment("Awarded Quotation", a.name, "Foundation board signed the minor-works contract; school holidays give us until the end of July.", "md", at(-180, 15))
	return a.name, p.name


def variation(award):
	with as_user("pm"):
		vo = frappe.get_doc({"doctype": "Variation Order", "subject": "Roof sheeting extended over the veranda", "variation_type": "Addition",
		                     "awarded_quotation": award, "vo_date": day(-140),
		                     "items": [{"description": "Roof sheeting and purlins over the veranda", "wbs": ROOT, "qty": 60, "uom": "Square Meter", "rate": 31}]})
		vo.flags.ignore_permissions = True
		vo.insert()
		for status in ("Submitted to Client", "Approved"):
			vo.status = status
			if status == "Approved":
				vo.approved_date = day(-133)
			vo.save()
	frappe.db.set_value("Variation Order", vo.name, {"submitted_date": day(-139), "approved_by": user("pm")},
	                    update_modified=False)
	return vo.name


def certificate(award, lines, start, end, quantities, sent, certified, invoiced):
	with as_user("qs"):
		ipc = frappe.get_doc({"doctype": "Client IPC", "awarded_quotation": award, "period_from": start, "period_to": end,
		                      "items": [dict(l) for l in lines]})
		certify = {}
		for row in ipc.items:
			q = next((v for k, v in quantities.items() if row.description.startswith(k)), 0)
			claimed, cert = q if isinstance(q, tuple) else (q, q)
			row.this_period_qty = claimed
			if cert != claimed:
				certify[row.line_key] = cert
		ipc.items = [r for r in ipc.items if r.this_period_qty or r.previous_qty]
		ipc.flags.ignore_permissions = True
		ipc.insert()
		ipc.status = "Submitted to Client"
		ipc.save()
		for row in ipc.items:
			if row.line_key in certify:
				row.certified_qty = certify[row.line_key]
		ipc.save()
		ipc.submit()
	frappe.db.set_value("Client IPC", ipc.name, {"creation": at(sent, 10), "submitted_on": day(sent), "modified": at(certified, 15)},
	                    update_modified=False)
	with as_user("finance"):
		from a3_constructa.api.client_billing import invoice_for_ipc

		si = submit_on(invoice_for_ipc(ipc.name), invoiced, due=invoiced + 30)
	return ipc.name, si


def submit_on(name, when, due):
	si = frappe.get_doc("Sales Invoice", name)
	si.update({"set_posting_time": 1, "posting_date": day(when), "due_date": day(due)})
	si.payment_schedule = []
	si.flags.ignore_permissions = True
	si.save()
	si.submit()
	return si.name


def receive(invoice, when, reference):
	pe = get_payment_entry("Sales Invoice", invoice, bank_account=acc("Rawbank USD"))
	pe.update({"posting_date": day(when), "reference_no": reference, "reference_date": day(when),
	           "remarks": f"Fondation Lisanga transfer {reference} for {invoice}."})
	with as_user("finance"):
		pe.flags.ignore_permissions = True
		pe.insert()
		pe.submit()
	return pe.name


def final_account(award):
	with as_user("qs"):
		fa = frappe.get_doc({"doctype": "Final Account", "awarded_quotation": award, "account_date": day(-30),
		                     "adjustments": [{"description": d, "amount": amt, "agreed": ok} for d, amt, ok in ADJUSTMENTS]})
		fa.flags.ignore_permissions = True
		fa.insert()
	frappe.db.set_value("Final Account", fa.name, {"creation": at(-30, 11), "modified": at(-30, 11)}, update_modified=False)
	comment("Final Account", fa.name, "Rock claim stays open: the engineer wants the dig photos before he will price it.", "qs", at(-21, 9))
	with as_user("md"):
		fa = frappe.get_doc("Final Account", fa.name)
		fa.account_date = day(-14)
		fa.flags.ignore_permissions = True
		fa.save()
		fa.submit()
	comment("Final Account", fa.name, "Agreed and signed with the foundation's engineer; the rock claim is left out.", "md", at(-14, 16))
	with as_user("finance"):
		from a3_constructa.api.client_billing import final_invoice

		si = submit_on(final_invoice(fa.name), -13, due=17)
	fa = frappe.get_doc("Final Account", fa.name)
	fa.run_method("onload")
	return fa.name, si
