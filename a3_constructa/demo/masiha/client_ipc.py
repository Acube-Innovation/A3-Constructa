# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-04C: the Administrative Centre billed by interim payment certificates.

- The 10% advance ($114,520) was paid in May against Rawbank guarantee
  RAW-BG-2026-118; it is billed as an advance invoice.
- IPC 1 is the opening certificate: the August progress claim ACC-SINV-2026-00006
  (30% of earthworks and frame), already invoiced before certificates were kept.
- IPC 2 (August-September): earthworks finished, frame to 60%, 200 m² of ground-floor
  tiling claimed; the engineer certifies 180 m². 5% retention, 20% advance recovery.
  Finance invoices it.
- IPC 3 (October): frame to 70%, doors 25%: with the client.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, as_user, at, comment, day, log

GUARANTEE_NO = "RAW-BG-2026-118"


def run():
	award = frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "title": ["like", "%Administrative Centre%"]}, "name")
	if not award:
		log("no Administrative Centre award")
		return
	if frappe.db.exists("Client IPC", {"awarded_quotation": award}):
		log("client IPCs already present")
		return
	from a3_constructa.api.client_billing import make_advance_invoice

	if not frappe.db.exists("Bank", "Rawbank"):
		frappe.get_doc({"doctype": "Bank", "bank_name": "Rawbank"}).insert(ignore_permissions=True)
	a = frappe.get_doc("Awarded Quotation", award)
	with as_user("finance"):
		bg = frappe.get_doc({"doctype": "Bank Guarantee", "bg_type": "Receiving", "customer": CUSTOMER, "project": a.project,
		                     "reference_doctype": "Awarded Quotation", "reference_docname": award, "bank": "Rawbank",
		                     "name_of_beneficiary": COMPANY, "bank_guarantee_number": GUARANTEE_NO,
		                     "amount": round(a.contract_value * a.advance_percent / 100, 2), "start_date": a.award_date, "end_date": day(240)})
		bg.flags.ignore_permissions = True
		bg.insert(); bg.submit()
		adv = frappe.get_doc("Sales Invoice", make_advance_invoice(award, bg.name))
		adv.update({"set_posting_time": 1, "posting_date": day(-155), "due_date": day(-125)})
		adv.payment_schedule = []
		adv.flags.ignore_permissions = True
		adv.save(); adv.submit()
	settle_advance(adv.name)

	lines = None
	with as_user("qs"):
		from a3_constructa.a3_constructa.doctype.client_ipc.client_ipc import get_contract_lines
		lines = get_contract_lines(award)
	ipc1 = certificate(award, lines, "2026-05-05", "2026-07-31", {"A1": 0.3, "A2": 0.3}, opening=frappe.db.get_value(
		"Sales Invoice", {"project": a.project, "docstatus": 1, "is_advance_invoice": 0, "client_ipc": ["is", "not set"]}, "name", order_by="posting_date asc"))
	ipc2 = certificate(award, lines, "2026-08-01", "2026-09-30", {"A1": 0.7, "A2": 0.3, "B2": 200}, certify={"B2": 180}, sent=-6, certified=-3)
	with as_user("finance"):
		from a3_constructa.api.client_billing import invoice_for_ipc

		si = frappe.get_doc("Sales Invoice", invoice_for_ipc(ipc2))
		si.update({"set_posting_time": 1, "posting_date": day(-2), "due_date": day(28)})
		si.payment_schedule = []
		si.flags.ignore_permissions = True
		si.save(); si.submit()
	comment("Client IPC", ipc2, "Engineer certified 180 m² of the 200 m² tiling claimed: skirtings at the stair still open.", "qs", at(-3, 16))
	ipc3 = certificate(award, lines, "2026-10-01", "2026-10-31", {"A2": 0.1, "B1": 0.25}, sent=0, submit=False)
	wc = subcontract_certificate(a.project)
	log(f"Advance {adv.name} ({bg.name}); {ipc1} opening; {ipc2} certified and invoiced as {si.name}; {ipc3} with the client; {wc}")


def certificate(award, lines, start, end, claimed, certify=None, opening=None, sent=None, certified=None, submit=True):
	with as_user("qs"):
		ipc = frappe.get_doc({"doctype": "Client IPC", "awarded_quotation": award, "period_from": start, "period_to": end,
		                      "opening_invoice": opening, "items": [dict(l) for l in lines]})
		for row in ipc.items:
			row.this_period_qty = claimed.get(row.line_ref, 0)
			if row.line_ref == "B2":
				row.wbs = "MSS-W-FL-A"  # the ground floor
		ipc.flags.ignore_permissions = True
		ipc.insert()
		ipc.items = [r for r in ipc.items if r.this_period_qty or r.previous_qty]
		ipc.status = "Submitted to Client"
		ipc.save()
		for row in ipc.items:
			if certify and row.line_ref in certify:
				row.certified_qty = certify[row.line_ref]
		ipc.save()
		if submit:
			ipc.submit()
	when = at(sent if sent is not None else -60, 10)
	frappe.db.set_value("Client IPC", ipc.name, {"creation": when, "submitted_on": when.date(),
	                                             "modified": at(certified, 15) if certified is not None else when},
	                    update_modified=False)
	return ipc.name


def settle_advance(invoice):
	"""The May payment of $114,520 was the advance. The finance stage, written before
	advance invoices existed, matched it to the first progress claim; it belongs to the
	advance invoice, so it is moved there (ERPNext's Unreconcile Payment, then Payment
	Reconciliation)."""
	pe = frappe.db.get_value("Payment Entry", {"reference_no": "GPE-TRF-2026-0311", "docstatus": 1}, "name")
	if not pe:
		return
	claims = [r.reference_name for r in frappe.get_all("Payment Entry Reference", filters={"parent": pe, "reference_doctype": "Sales Invoice"},
	                                                     fields=["reference_name"]) if r.reference_name != invoice]
	if claims:
		un = frappe.get_doc({"doctype": "Unreconcile Payment", "company": COMPANY, "voucher_type": "Payment Entry", "voucher_no": pe})
		un.add_references()
		un.allocations = [x for x in un.allocations if x.reference_name in claims]
		un.flags.ignore_permissions = True
		un.insert(); un.submit()
	pr = frappe.get_doc("Payment Reconciliation")
	pr.update({"company": COMPANY, "party_type": "Customer", "party": CUSTOMER,
	           "receivable_payable_account": frappe.get_cached_value("Company", COMPANY, "default_receivable_account")})
	pr.get_unreconciled_entries()
	pay = [p for p in pr.payments if p.reference_name == pe]
	inv = [i for i in pr.invoices if i.invoice_number == invoice]
	if pay and inv:
		pr.allocate_entries(frappe._dict(payments=[pay[0].as_dict()], invoices=[inv[0].as_dict()]))
		pr.reconcile()


def subcontract_certificate(project):
	"""The other direction of the Retention Ledger: we hold 10% from the tiling subcontractor."""
	po = frappe.db.get_value("Purchase Order Item", {"item_code": "SVC-TILE-INST", "docstatus": 1}, ["parent", "qty", "rate", "wbs", "cost_code"], as_dict=True)
	if not po or frappe.db.exists("Work Certificate", {"subcontract_po": po.parent}):
		return None
	supplier = frappe.db.get_value("Purchase Order", po.parent, "supplier")
	with as_user("pm"):
		wc = frappe.get_doc({"doctype": "Work Certificate", "project": project, "supplier": supplier, "subcontract_po": po.parent,
		                     "wbs": po.wbs, "cost_head": frappe.db.get_value("WBS", po.wbs, "cost_head"), "certificate_no": "ETW-01",
		                     "period_from": day(-60), "period_to": day(-5),
		                     "items": [{"item_code": "SVC-TILE-INST", "cost_code": po.cost_code, "contracted_qty": po.qty, "previous_qty": 0,
		                                "this_period_qty": 180, "rate": po.rate, "retention_percent": 10}]})
		# P-09B: the documents the tiler lodged; checked as of the day it was certified.
		from a3_constructa.demo.masiha.subcontract_compliance import tiler_documents

		for row in tiler_documents():
			wc.append("compliance", row)
		wc.flags.compliance_as_of = day(-3)
		wc.flags.ignore_permissions = True
		wc.insert(); wc.submit()
	return f"{wc.name}: 180 m² tiling certified to {supplier}, ${wc.total_retention:,.2f} retention held"
