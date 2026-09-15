# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo finance: supplier bills, a progress claim to the client, and retention.

The numbers here are what make the Finance dashboard mean something: payables
and receivables with real ageing, retention sitting on its own account, and one
invoice left unpaid past its due date so the overdue card is not zero.
"""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import account, company, day, log
from a3_constructa.demo.masters import _project

RETENTION_FRAGMENT = "Retention Payable"


def run():
	bill_purchase_receipts()
	create_client_invoices()
	post_retention()
	pay_one_supplier()
	receive_one_payment()


def bill_purchase_receipts():
	"""Invoice the goods already received, so payables age from the GRN date."""
	if frappe.db.exists("Purchase Invoice", {"docstatus": 1}):
		log("purchase invoices already present")
		return

	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

	receipts = frappe.get_all("Purchase Receipt", filters={"docstatus": 1}, pluck="name")
	made = 0
	for receipt in receipts:
		try:
			doc = make_purchase_invoice(receipt)
			doc.posting_date = day(-8)
			doc.set_posting_time = 1
			# Left unpaid and past due, so the ageing and overdue figures bite.
			doc.due_date = day(-1)
			doc.flags.ignore_permissions = True
			doc.insert()
			doc.submit()
			made += 1
		except Exception as exc:
			log("could not bill %s: %s" % (receipt, str(exc)[:70]))
	log("purchase invoices: %d" % made)


def create_client_invoices():
	"""A progress claim to the client - head 72's revenue recognition."""
	if frappe.db.exists("Sales Invoice", {"docstatus": 1}):
		log("sales invoices already present")
		return

	customer = _customer()
	if not customer:
		log("no customer available; sales invoices skipped")
		return

	income = account("", hint="Sales", root_type="Income") or account("", root_type="Income")
	cost_center = frappe.get_all("Cost Center", filters={
		"company": company(), "is_group": 0}, pluck="name")[0]

	# Two claims: one settled, one still outstanding and now overdue.
	for amount, posted, due, description in [
		(185000, -55, -25, "Progress claim 01 - substructure"),
		(142000, -20, -2, "Progress claim 02 - superstructure to first lift"),
	]:
		doc = frappe.new_doc("Sales Invoice")
		doc.customer = customer
		doc.company = company()
		doc.posting_date = day(posted)
		doc.set_posting_time = 1
		doc.due_date = day(due)
		doc.project = _project()
		doc.append("items", {
			"item_name": description, "description": description,
			"qty": 1, "rate": amount, "income_account": income,
			"cost_center": cost_center, "uom": "Nos",
			"project": _project(),
		})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert()
		doc.submit()
		log("sales invoice %s: %s due %s" % (doc.name, flt(doc.grand_total), doc.due_date))


def _customer():
	name = "Mbandaka Provincial Authority"
	if not frappe.db.exists("Customer", name):
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		frappe.get_doc({
			"doctype": "Customer", "customer_name": name,
			"customer_group": group, "territory": territory,
			"customer_type": "Company",
		}).insert(ignore_permissions=True)
	return name


def post_retention():
	"""Move the certified retention onto the Retention Payable account.

	The Legend routes retention there so it can be released at defect-liability
	expiry rather than paid with the certificate. This is the journal that puts
	it on the balance sheet, and what the "Retention Held" card reads.
	"""
	if frappe.db.exists("Journal Entry", {"user_remark": ["like", "%retention%"]}):
		log("retention journal already present")
		return

	retention_account = frappe.get_all("Account", filters={
		"company": company(), "name": ["like", "%" + RETENTION_FRAGMENT + "%"]}, pluck="name")
	if not retention_account:
		log("no retention account; journal skipped")
		return

	certificate = frappe.db.get_value(
		"Work Certificate", {"docstatus": 1},
		["name", "total_retention", "supplier"], as_dict=True
	)
	if not certificate or not flt(certificate.total_retention):
		log("no certified retention to post")
		return

	expense = account("", hint="Cost of Goods", root_type="Expense") or account(
		"", root_type="Expense")
	cost_center = frappe.get_all("Cost Center", filters={
		"company": company(), "is_group": 0}, pluck="name")[0]

	doc = frappe.new_doc("Journal Entry")
	doc.voucher_type = "Journal Entry"
	doc.company = company()
	doc.posting_date = day(-9)
	doc.user_remark = "Subcontractor retention withheld on %s" % certificate.name
	doc.append("accounts", {
		"account": expense, "debit_in_account_currency": flt(certificate.total_retention),
		"cost_center": cost_center, "project": _project(),
	})
	# Retention Payable is a party account: the money is owed to the
	# subcontractor it was withheld from, not to payables in general.
	doc.append("accounts", {
		"account": retention_account[0],
		"party_type": "Supplier", "party": certificate.supplier,
		"credit_in_account_currency": flt(certificate.total_retention),
		"cost_center": cost_center, "project": _project(),
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("retention journal %s: %s held" % (doc.name, flt(certificate.total_retention)))


def pay_one_supplier():
	"""Settle one bill so payables are not all outstanding."""
	if frappe.db.exists("Payment Entry", {"payment_type": "Pay", "docstatus": 1}):
		log("supplier payment already present")
		return

	invoice = frappe.db.get_value(
		"Purchase Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]},
		["name", "outstanding_amount"], as_dict=True)
	if not invoice:
		log("nothing to pay")
		return

	_make_payment("Purchase Invoice", invoice.name, "Pay", invoice.outstanding_amount, -4)


def receive_one_payment():
	"""Client settles the first progress claim; the second stays outstanding."""
	if frappe.db.exists("Payment Entry", {"payment_type": "Receive", "docstatus": 1}):
		log("customer receipt already present")
		return

	invoice = frappe.db.get_value(
		"Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]},
		["name", "outstanding_amount"], as_dict=True, order_by="posting_date asc")
	if not invoice:
		log("nothing to receive")
		return

	_make_payment("Sales Invoice", invoice.name, "Receive", invoice.outstanding_amount, -18)


def _make_payment(doctype, name, payment_type, amount, when):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	bank = account("Bank") or account("Cash")
	if not bank:
		log("no bank or cash account; payment skipped")
		return

	doc = get_payment_entry(doctype, name)
	doc.posting_date = day(when)
	doc.reference_no = "DEMO/%s" % name
	doc.reference_date = day(when)
	if payment_type == "Pay":
		doc.paid_from = bank
	else:
		doc.paid_to = bank
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	log("%s %s: %s against %s" % (payment_type.lower(), doc.name, flt(amount), name))
