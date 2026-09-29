# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Step 20: invoices matched to orders and receipts, and the money that moves.

Supplier side: the Spanish invoice matched to the receipt with the 30% advance
adjusted and put on hold until the credit note for the broken tiles arrives;
local invoices with VAT, one paid, one part paid; the excavator paid.
Client side: the 10% advance and the first progress claim.
"""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice
from frappe.utils import flt

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, acc, as_user, at, comment, day, exists, log

VAT = "DRC VAT 16% - MSS"


def run():
	client_advance()
	client_claim()
	import_invoice()
	local_invoices()
	equipment_invoice()
	frappe.db.commit()


def _terms_from(pi, bill_date):
	"""Date the bill and rebuild its payment schedule from the terms, for that date."""
	pi.bill_date = bill_date
	pi.payment_schedule = []
	pi.due_date = None


def _pay(doctype, name, when, amount=None, reference="", remarks=""):
	pe = get_payment_entry(doctype, name, party_amount=amount, bank_account=acc("Rawbank USD"))
	pe.posting_date = day(when)
	pe.reference_no = reference or f"RWB-{abs(when):03d}-{name[-5:]}"
	pe.reference_date = day(when)
	pe.remarks = remarks
	with as_user("finance"):
		pe.insert()
		pe.submit()
	return pe


def client_advance():
	so = frappe.db.get_value("Sales Order", {"customer": CUSTOMER, "company": COMPANY, "docstatus": 1}, "name")
	if exists("Payment Entry", {"party": CUSTOMER, "company": COMPANY, "docstatus": 1}):
		return
	_pay("Sales Order", so, -140, 114520, "GPE-TRF-2026-0311", "10% contract advance received from the client.")
	log("client advance: $114,520 (10%) received")


def client_claim():
	if exists("Sales Invoice", {"customer": CUSTOMER, "company": COMPANY, "docstatus": 1}):
		return
	so = frappe.db.get_value("Sales Order", {"customer": CUSTOMER, "company": COMPANY, "docstatus": 1}, "name")
	si = make_sales_invoice(so)
	si.posting_date = day(-40)
	si.set_posting_time = 1
	si.due_date = day(-10)
	si.items = [row for row in si.items if row.item_code == "CW-STRUCT"]
	si.items[0].qty = 30
	si.remarks = "Progress claim 1: mobilisation and substructure complete, 30% of the structural works."
	si.set_advances()
	for row in si.advances:
		row.allocated_amount = row.advance_amount
	with as_user("finance"):
		si.insert()
		si.submit()
	_pay("Sales Invoice", si.name, -12, 120000, "GPE-TRF-2026-0487", "Part payment of progress claim 1.")
	log(f"progress claim {si.name}: ${flt(si.grand_total):,.0f}, advance deducted, $120,000 received")


def import_invoice():
	receipt = frappe.db.get_value("Purchase Receipt", {"supplier": "Iberica Ceramica S.L.", "company": COMPANY,
	                                                   "docstatus": 1}, "name")
	if exists("Purchase Invoice", {"supplier": "Iberica Ceramica S.L.", "company": COMPANY, "docstatus": 1}):
		return
	pi = make_purchase_invoice(receipt)
	pi.posting_date = day(-8)
	pi.set_posting_time = 1
	pi.bill_no = "IBC-INV-7731"
	# Received with the goods; the schedule is rebuilt from the 30/70 terms for that date.
	_terms_from(pi, day(-12))
	pi.set_advances()
	for row in pi.advances:
		row.allocated_amount = row.advance_amount
	with as_user("finance"):
		pi.insert()
		pi.submit()
		# A hold is placed on a submitted invoice, the way the form's "Block Invoice" does it.
		pi.block_invoice("Hold: 10 m2 rejected at receipt. Awaiting Iberica's credit note before paying "
		                 "the balance.", day(14))
	comment("Purchase Invoice", pi.name, "Three-way match done: invoice lines agree with the order rates and the "
	        "accepted receipt quantities (690 m2, not the 700 shipped). 30% advance adjusted. Payment held for the "
	        "credit note.", "finance", at(-8, 15))
	log(f"import invoice {pi.name}: EUR {flt(pi.grand_total):,.2f}, advance adjusted, on hold")


def local_invoices():
	if exists("Purchase Invoice", {"supplier": "Congo Steel & Cement SARL", "company": COMPANY, "docstatus": 1}):
		return
	receipts = frappe.get_all("Purchase Receipt", filters={"supplier": "Congo Steel & Cement SARL", "company": COMPANY,
	                                                       "docstatus": 1}, pluck="name", order_by="posting_date")
	for receipt, when, bill, paid_when, share in ((receipts[0], -70, "CSC-F-2026-0331", -40, 1.0),
	                                              (receipts[1], -43, "CSC-F-2026-0412", -18, 0.5)):
		pi = make_purchase_invoice(receipt)
		pi.posting_date = day(when)
		pi.set_posting_time = 1
		pi.bill_no = bill
		_terms_from(pi, day(when))
		pi.taxes_and_charges = VAT
		pi.set_taxes()
		with as_user("finance"):
			pi.insert()
			pi.submit()
		_pay("Purchase Invoice", pi.name, paid_when, flt(pi.grand_total * share, 2),
		     remarks="Paid in full." if share == 1 else "Part payment, 50%; balance due next cycle.")
	log("local invoices: two with 16% VAT, one paid in full, one 50% paid")


def equipment_invoice():
	receipt = frappe.db.get_value("Purchase Receipt", {"supplier": "Equipements Lourds du Congo SARL",
	                                                   "company": COMPANY, "docstatus": 1}, "name")
	if exists("Purchase Invoice", {"supplier": "Equipements Lourds du Congo SARL", "company": COMPANY, "docstatus": 1}):
		return
	pi = make_purchase_invoice(receipt)
	pi.posting_date = day(-58)
	pi.set_posting_time = 1
	pi.bill_no = "ELC-FAC-2026-117"
	_terms_from(pi, day(-60))
	with as_user("finance"):
		pi.insert()
		pi.submit()
	_pay("Purchase Invoice", pi.name, -50, remarks="Excavator paid in full.")
	log(f"equipment invoice {pi.name}: ${flt(pi.grand_total):,.0f}, paid")
