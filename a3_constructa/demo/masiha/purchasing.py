# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Steps 8, 14, 15 and the order for step 19: the four ways the approved lines are bought.

International (tiles from Spain): RFQ to two suppliers, quotations with a
technical evaluation, the recommended one ordered in euros FOB Valencia,
approved, released, acknowledged, and 30% paid in advance. The order is the
consolidated 1,000 m2 of the client's diagram: one item, two lines, 600 on
WBS A and 400 on WBS B.

Local (cement and steel): RFQ, comparison, order delivered straight to site.
Equipment (the excavator): ordered straight from the approved request.
Cash (discs and spacers bought at a Mbandaka hardware shop): a PUR-CASH
regularization order and one paid bill that also receives the stock, so there
is no second receipt and no second payment.
"""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
from erpnext.buying.doctype.request_for_quotation.request_for_quotation import make_supplier_quotation_from_rfq
from erpnext.buying.doctype.supplier_quotation.supplier_quotation import make_purchase_order as po_from_quote
from erpnext.stock.doctype.material_request.material_request import make_purchase_order as po_from_request
from erpnext.stock.doctype.material_request.material_request import make_request_for_quotation
from frappe.utils import flt, getdate

from a3_constructa.demo.masiha.common import (
	BUYING_PRICE_LIST,
	COMPANY,
	acc,
	as_user,
	assign,
	at,
	comment,
	day,
	exists,
	insert,
	log,
	project,
	transition,
	wh,
)

FLOORING_REQUEST = "Flooring materials, ground and first floor"
STRUCTURAL_REQUEST = "Cement and reinforcement, frame"
EXCAVATOR_REQUEST = "Excavator 20 t for earthworks"
IMPORT_ITEMS = ("FIN-POR-600", "FIN-ADH-C2", "FIN-GRT-CG2")
CASH_ITEMS = ("FIN-DSC-230", "FIN-SPC-3")


def request(title):
	return frappe.db.get_value("Material Request", {"title": title, "company": COMPANY, "docstatus": 1}, "name")


def run():
	fund_accounts()
	international_order()
	local_order()
	equipment_order()
	cash_purchase()
	frappe.db.commit()


def fund_accounts():
	"""Opening capital in the bank and a petty-cash float, so payments have something to come from."""
	if exists("Journal Entry", {"company": COMPANY, "user_remark": "Opening capital and petty cash float"}):
		return
	insert({"doctype": "Journal Entry", "company": COMPANY, "posting_date": day(-172), "voucher_type": "Journal Entry",
	        "user_remark": "Opening capital and petty cash float",
	        "accounts": [{"account": acc("Rawbank USD"), "debit_in_account_currency": 748000},
	                     {"account": acc("Cash"), "debit_in_account_currency": 2000},
	                     {"account": acc("Capital Stock"), "credit_in_account_currency": 750000}]}, submit=True)
	log("opening capital: $748,000 at Rawbank, $2,000 petty cash")


def _rfq(request_name, items, suppliers, when, message):
	rfq = make_request_for_quotation(request_name)
	rfq.items = [row for row in rfq.items if row.item_code in items]
	rfq.transaction_date = day(when)
	rfq.message_for_supplier = message
	rfq.suppliers = []
	for supplier in suppliers:
		rfq.append("suppliers", {"supplier": supplier, "send_email": 0})
	# The buyer prepares the RFQ; the procurement manager sends it.
	with as_user("buyer"):
		rfq.insert()
	with as_user("procurement"):
		rfq = frappe.get_doc("Request for Quotation", rfq.name)
		rfq.submit()
	return rfq


def _quote(rfq, supplier, when, rates, evaluation, remarks, recommended, recommendation, currency=None, extra=None):
	sq = make_supplier_quotation_from_rfq(rfq.name, for_supplier=supplier)
	sq.transaction_date = day(when)
	sq.valid_till = day(when + 60)
	if currency:
		sq.currency = currency
	for row in sq.items:
		row.rate = rates[row.item_code]
	sq.technical_evaluation_status = evaluation
	sq.technical_remarks = remarks
	sq.is_recommended = recommended
	sq.recommendation_remarks = recommendation
	sq.update(extra or {})
	with as_user("buyer"):
		sq.insert()
		sq.submit()
	return sq


def _approve_and_release(po_name, when, approval_note, release_note):
	transition("Purchase Order", po_name, "Submit for Approval", "buyer", at(when, 9))
	transition("Purchase Order", po_name, "Approve", "procurement", at(when, 15), approval_note)
	transition("Purchase Order", po_name, "Release to Supplier", "buyer", at(when + 1, 10), release_note)


# ---------------------------------------------------------------- international
def international_order():
	if exists("Purchase Order", {"supplier": "Iberica Ceramica S.L.", "company": COMPANY}):
		log("international order already present")
		return
	mr = request(FLOORING_REQUEST)
	rfq = _rfq(mr, IMPORT_ITEMS, ["Iberica Ceramica S.L.", "Foshan Tile Export Co. Ltd."], -106,
	           "Please quote FOB for porcelain tiles 600x600 R10, adhesive C2TE and grout CG2 as per the attached "
	           "specification. State delivery lead time, packing and container count.")
	iberica = _quote(rfq, "Iberica Ceramica S.L.", -97, {"FIN-POR-600": 16.90, "FIN-ADH-C2": 8.80, "FIN-GRT-CG2": 5.70},
	                 "Qualified", "Samples pass: 10 mm thickness, water absorption 0.3%, R10 slip rating.", 1,
	                 "Recommended: fully compliant, 45-day lead time, lowest landed cost once duty on the Chinese "
	                 "adhesive is included.", currency="EUR")
	_quote(rfq, "Foshan Tile Export Co. Ltd.", -96, {"FIN-POR-600": 14.20, "FIN-ADH-C2": 7.10, "FIN-GRT-CG2": 4.60},
	       "Qualified with Conditions", "Sample thickness 8.5 mm against the 10 mm specified.", 0,
	       "Not recommended: thickness non-compliant; 70-day lead time misses the flooring programme.")
	comment("Request for Quotation", rfq.name, "Commercial comparison done (Supplier Quotation Comparison report). "
	        "Vendor selection: Iberica Ceramica, approved by Marie Kalala.", "procurement", at(-96, 16))

	po = po_from_quote(iberica.name)
	po.transaction_date = day(-95)
	po.schedule_date = day(-52)
	po.set_warehouse = wh("Central Store Kinshasa")
	po.incoterm = "FOB"
	po.named_place = "Valencia, Spain"
	po.payment_terms_template = "30% Advance, 70% on Delivery"
	po.terms = ("<p>Prices FOB Valencia. Sea freight, insurance, import duty and clearing are excluded and borne by "
	            "the buyer. Delivery in two shipments: tiles for WBS A with the adhesive first, the balance "
	            "with the grout. FAT at the factory before loading.</p>")
	for row in po.items:
		row.schedule_date = getdate(day(-52))
		row.warehouse = wh("Central Store Kinshasa")
	with as_user("buyer"):
		po.insert()
	_approve_and_release(po.name, -95,
	                     f"Approved. Commitment EUR {flt(po.grand_total):,.2f} (USD {flt(po.base_grand_total):,.2f}) "
	                     "against the flooring BOQ; one tile code, 600 m2 for WBS A and 400 m2 for WBS B.",
	                     "Released to Iberica by email with the specification and packing instructions.")
	frappe.db.set_value("Purchase Order", po.name, {"order_confirmation_no": "IBC-OC-2026-0418",
	                                                "order_confirmation_date": day(-91)}, update_modified=False)
	comment("Purchase Order", po.name, "Supplier acknowledged the order: IBC-OC-2026-0418.", "buyer", at(-91, 11))
	assign("Purchase Order", po.name, "logistics", "procurement", at(-93, 9),
	       "Expedite: production progress, FAT, cargo readiness, packing lists and dispatch advice.")

	_advance(po.name)
	log(f"international: RFQ {rfq.name}, 2 quotes, PO {po.name} EUR {flt(po.grand_total):,.2f} FOB Valencia, 30% advance")


def _advance(po_name):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	po = frappe.get_doc("Purchase Order", po_name)
	pe = get_payment_entry("Purchase Order", po_name, bank_account=acc("Rawbank USD"))
	advance = flt(po.grand_total * 0.30, 2)
	pe.posting_date = day(-88)
	pe.paid_from = acc("Rawbank USD")
	pe.received_amount = advance
	pe.target_exchange_rate = po.conversion_rate
	pe.paid_amount = flt(advance * po.conversion_rate, 2)
	pe.source_exchange_rate = 1
	pe.references[0].allocated_amount = advance
	pe.reference_no = "SWIFT-RWB-260088"
	pe.reference_date = day(-88)
	pe.remarks = "30% advance against the Iberica order, per the 30/70 payment terms."
	with as_user("finance"):
		pe.insert()
		pe.submit()


# ---------------------------------------------------------------- local route
def local_order():
	if exists("Purchase Order", {"supplier": "Congo Steel & Cement SARL", "company": COMPANY}):
		log("local order already present")
		return
	mr = request(STRUCTURAL_REQUEST)
	rfq = _rfq(mr, ("CEM-425-50", "STL-Y16"), ["Kinshasa Building Supplies SARL", "Congo Steel & Cement SARL"], -102,
	           "Please quote delivered to Mbandaka site: cement CEM II 42.5N and rebar Y16.")
	_quote(rfq, "Kinshasa Building Supplies SARL", -100, {"CEM-425-50": 11.60, "STL-Y16": 1010.00}, "Qualified",
	       "Certificates provided.", 0, "Higher price; delivery to Kinshasa only.")
	chosen = _quote(rfq, "Congo Steel & Cement SARL", -100, {"CEM-425-50": 11.05, "STL-Y16": 975.00}, "Qualified",
	                "Mill certificates for rebar; cement batch test reports.", 1,
	                "Recommended: lowest price and delivers by barge to Mbandaka.")
	po = po_from_quote(chosen.name)
	po.transaction_date = day(-99)
	po.schedule_date = day(-70)
	po.set_warehouse = wh("Mbandaka Site Store")
	po.payment_terms_template = "Net 30 Days"
	for row in po.items:
		row.schedule_date = getdate(day(-70))
		row.warehouse = wh("Mbandaka Site Store")
	with as_user("buyer"):
		po.insert()
	level = "level 1 (up to $25,000)" if po.base_grand_total <= 25000 else "level 2 (over $25,000)"
	_approve_and_release(po.name, -99, f"Approved at {level} of the approval matrix.",
	                     "Released to supplier; delivery direct to Mbandaka site in two lots.")
	log(f"local: RFQ {rfq.name}, PO {po.name} ${flt(po.grand_total):,.2f}, delivered direct to site")


# ---------------------------------------------------------------- equipment
def equipment_order():
	if exists("Purchase Order", {"supplier": "Equipements Lourds du Congo SARL", "company": COMPANY}):
		return
	po = po_from_request(request(EXCAVATOR_REQUEST))
	po.supplier = "Equipements Lourds du Congo SARL"
	po.transaction_date = day(-96)
	po.schedule_date = day(-62)
	po.payment_terms_template = "Net 30 Days"
	po.buying_price_list = BUYING_PRICE_LIST
	for row in po.items:
		row.rate = 142500
		row.schedule_date = getdate(day(-62))
	with as_user("buyer"):
		po.insert()
	_approve_and_release(po.name, -96, "Approved at level 2 of the matrix (over $25,000), with Didier Kasongo.",
	                     "Released; delivery to Kinshasa Central Yard with commissioning.")
	log(f"equipment: PO {po.name} for the excavator, ${flt(po.grand_total):,.0f}")


# ---------------------------------------------------------------- cash route
def cash_purchase():
	if exists("Purchase Order", {"supplier": "Quincaillerie du Fleuve", "company": COMPANY}):
		return
	mr = request(FLOORING_REQUEST)
	comment("Material Request", mr, "Cash purchase approved for the discs and spacers (petty cash, under the $400 "
	        "limit): buy locally at Mbandaka.", "pm", at(-81, 9))
	po = po_from_request(mr)
	po.items = [row for row in po.items if row.item_code in CASH_ITEMS]
	po.naming_series = "PUR-CASH-.YYYY.-"
	po.supplier = "Quincaillerie du Fleuve"
	po.transaction_date = day(-80)
	po.schedule_date = day(-80)
	po.buying_price_list = BUYING_PRICE_LIST
	for row in po.items:
		row.rate = {"FIN-DSC-230": 21.50, "FIN-SPC-3": 4.40}[row.item_code]
		row.schedule_date = getdate(day(-80))
		row.warehouse = wh("Mbandaka Site Store")
	with as_user("buyer"):
		po.insert()
	transition("Purchase Order", po.name, "Submit for Approval", "buyer", at(-80, 14))
	transition("Purchase Order", po.name, "Approve", "procurement", at(-80, 16),
	           "Regularization of cash purchase, bill QF-2231 from Quincaillerie du Fleuve.")

	# One bill that pays and receives: no separate receipt, no separate payment.
	pi = make_purchase_invoice(po.name)
	pi.posting_date = day(-80)
	pi.set_posting_time = 1
	pi.bill_no = "QF-2231"
	pi.bill_date = day(-81)
	pi.update_stock = 1
	pi.is_paid = 1
	pi.mode_of_payment = "Cash"
	pi.cash_bank_account = acc("Cash")
	for row in pi.items:
		row.warehouse = wh("Mbandaka Site Store")
	pi.paid_amount = pi.base_paid_amount = None
	with as_user("finance"):
		pi.insert()
		pi.paid_amount = pi.grand_total
		pi.base_paid_amount = pi.base_grand_total
		pi.save()
		pi.submit()
	comment("Purchase Invoice", pi.name, "Bill verified against the regularization PO: items, quantities and rates "
	        "match. Paid from petty cash; stock received at Mbandaka site on this bill.", "finance", at(-80, 17))
	log(f"cash: regularization PO {po.name} and paid bill {pi.name} (${flt(pi.grand_total):,.2f}), stock received on the bill")
