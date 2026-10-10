# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01D: WBS and cost code through invoices, journals, expenses and the GL.

- Tiling labour: an order to the tiling subcontractor for 200 m² on WBS A, and
  its invoice made from the order. The invoice line keeps WBS A and cost code
  Floor finishes - installation, posts to the cost code's account (Project
  Services) and shows in Cost Code Wise Costing as actual cost.
- Grout: 20 bags ordered and received for WBS B, but the supplier invoiced 18
  (two bags arrived split). The invoice is left as a draft, flagged "Qty
  differs". A rate difference is refused outright on this site by ERPNext's own
  Buying Settings > Maintain Same Rate.
- A journal for generator hire on the substructure, booked with cost code Plant
  and equipment, and a site engineer's travel claim on the same WBS.
- An Inactive cost code that no document can use.
"""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice, make_purchase_receipt
from frappe.utils import flt, getdate

from a3_constructa.demo.masiha.common import COMPANY, acc, as_user, at, comment, cost_center, day, exists, insert, log, project, user, wh
from a3_constructa.demo.masiha.purchasing import _approve_and_release

TILER = "Equateur Tiling Works SARL"
GROUT_SUPPLIER = "Kinshasa Building Supplies SARL"


def run():
	inactive_cost_code()
	tiling_labour()
	grout_rate_mismatch()
	generator_journal()
	travel_claim()


def inactive_cost_code():
	if frappe.db.exists("Cost Code", "MSS-CC-FWK-OLD"):
		return
	insert({"doctype": "Cost Code", "cost_code": "MSS-CC-FWK-OLD", "category": "Rental", "status": "Inactive",
	        "description": "Formwork hire - old framework agreement (closed March 2026)",
	        "account": acc("Plant and Equipment Costs"), "cost_center": cost_center()})
	log("cost code MSS-CC-FWK-OLD: Inactive")


def _order(supplier, item, qty, rate, wbs, cost_code, when, warehouse=None):
	po = frappe.get_doc({
		"doctype": "Purchase Order", "company": COMPANY, "supplier": supplier, "transaction_date": day(when),
		"schedule_date": day(when + 14), "project": project(),
		"items": [{"item_code": item, "qty": qty, "rate": rate, "schedule_date": getdate(day(when + 14)),
		           "project": project(), "wbs": wbs, "cost_code": cost_code,
		           **({"warehouse": warehouse} if warehouse else {})}],
	})
	po.flags.ignore_permissions = True
	with as_user("buyer"):
		po.insert()
	_approve_and_release(po.name, when, "Approved at level 1 of the approval matrix.", "Released to the supplier.")
	return frappe.get_doc("Purchase Order", po.name)


def tiling_labour():
	if exists("Purchase Invoice", {"bill_no": "ETW-0147", "company": COMPANY}):
		return
	if not frappe.db.exists("Supplier", TILER):
		insert({"doctype": "Supplier", "supplier_name": TILER, "supplier_group": frappe.db.exists("Supplier Group", "Services") or "All Supplier Groups", "country": "Congo, The Democratic Republic of the"})
	po = _order(TILER, "SVC-TILE-INST", 200, 7.50, "MSS-W-FL-A", "MSS-CC-FIN-S", -20)
	pi = make_purchase_invoice(po.name)
	pi.posting_date = day(-6)
	pi.set_posting_time = 1
	pi.bill_no = "ETW-0147"
	pi.bill_date = day(-7)
	pi.due_date = None
	pi.payment_schedule = []
	pi.flags.silent_three_way = True
	with as_user("finance"):
		pi.insert(ignore_permissions=True)
		pi.submit()
	comment("Purchase Invoice", pi.name, "First valuation: 200 m² laid on the ground floor offices.", "qs", at(-6, 11))
	log(f"tiling labour: PO {po.name}, invoice {pi.name} ${flt(pi.grand_total):,.2f} on WBS A / Floor finishes - installation")


def grout_rate_mismatch():
	if exists("Purchase Invoice", {"bill_no": "KBS-5520", "company": COMPANY}):
		return
	po = _order(GROUT_SUPPLIER, "FIN-GRT-CG2", 20, 6.40, "MSS-W-FL-B", "MSS-CC-FIN-M", -15, wh("Mbandaka Site Store"))
	pr = make_purchase_receipt(po.name)
	pr.posting_date = day(-10)
	pr.set_posting_time = 1
	with as_user("stores"):
		pr.insert(ignore_permissions=True)
		pr.submit()
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice as pi_from_pr

	pi = pi_from_pr(pr.name)
	pi.posting_date = day(-3)
	pi.set_posting_time = 1
	pi.bill_no = "KBS-5520"
	pi.bill_date = day(-4)
	pi.due_date = None
	pi.payment_schedule = []  # recomputed from the invoice date, not the receipt's
	for row in pi.items:
		row.qty = 18  # two of the twenty bags arrived split
	pi.flags.silent_three_way = True
	with as_user("finance"):
		pi.insert(ignore_permissions=True)
	comment("Purchase Invoice", pi.name, "On hold: 20 bags received, 18 billed. Checking with stores whether the two split bags were returned.", "finance", at(-3, 14))
	log(f"grout: PO {po.name}, receipt {pr.name}, invoice {pi.name} draft, flagged Qty differs")


def generator_journal():
	if exists("Journal Entry", {"company": COMPANY, "user_remark": ["like", "Generator hire%"]}):
		return
	je = frappe.get_doc({
		"doctype": "Journal Entry", "company": COMPANY, "posting_date": day(-12), "voucher_type": "Journal Entry",
		"user_remark": "Generator hire, site office and batching plant, 3 weeks (paid cash).",
		"accounts": [
			{"account": acc("Miscellaneous Expenses"), "debit_in_account_currency": 1350, "project": project(),
			 "wbs": "MSS-W-ES", "cost_code": "MSS-CC-PLT"},
			{"account": acc("Cash"), "credit_in_account_currency": 1350},
		],
	})
	with as_user("finance"):
		je.insert(ignore_permissions=True)
		je.submit()
	log(f"journal {je.name}: generator hire $1,350 on WBS MSS-W-ES, posted to {je.accounts[0].account}")


def travel_claim():
	employee = frappe.db.get_value("Employee", {"user_id": user("requester")}, "name")
	if not employee or exists("Expense Claim", {"employee": employee, "company": COMPANY}):
		return
	if not frappe.db.get_value("Company", COMPANY, "default_expense_claim_payable_account"):
		frappe.db.set_value("Company", COMPANY, "default_expense_claim_payable_account", acc("Creditors"))
	travel = frappe.get_doc("Expense Claim Type", "Travel")
	if not any(a.company == COMPANY for a in travel.accounts):
		travel.append("accounts", {"company": COMPANY, "default_account": acc("Travel Expenses")})
		travel.save(ignore_permissions=True)
	claim = frappe.get_doc({
		"doctype": "Expense Claim", "company": COMPANY, "employee": employee, "posting_date": day(-8),
		"expense_approver": user("pm"), "approval_status": "Approved", "project": project(),
		"payable_account": acc("Creditors"),
		"expenses": [{"expense_date": day(-9), "expense_type": "Travel", "amount": 186, "sanctioned_amount": 186,
		              "description": "Boat fare Kinshasa-Mbandaka to inspect the rebar delivery",
		              "project": project(), "wbs": "MSS-W-ES", "cost_code": "MSS-CC-SITE"}],
	})
	with as_user("pm"):
		claim.insert(ignore_permissions=True)
		claim.submit()
	log(f"expense claim {claim.name}: $186 travel on WBS MSS-W-ES, posted to {claim.expenses[0].default_account}")
