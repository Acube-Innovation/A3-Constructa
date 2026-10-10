# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Subcontractor billing from a Work Certificate - catalogue 9.6.

The purchase invoice of a submitted certificate:
- a line per certificate line, at the certified quantity and rate, with the
  project, the certificate's WBS and the line's cost code, against the
  subcontract PO line so the order shows it billed;
- each deduction as a "Deduct" row of the invoice's taxes, to Subcontract
  Back-charges on the deduction's WBS and cost code. ERPNext refuses a negative
  item rate unless negative rates are switched on for every selling and buying
  document, so the deductions sit with the taxes, where a deduction is native;
- retention, which is still owed to the subcontractor and so must name them on
  Retention Payable (a payable account): when the invoice is submitted, a journal
  moves it from the supplier's payable on the invoice to Retention Payable.

Cancelling the invoice cancels that journal; cancelling or deleting it frees the
certificate to be invoiced again.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.setup.install_defaults import BACK_CHARGES, RETENTION_ACCOUNT_NAME, contract_account


def _account(company, name):
	account = contract_account(company, name)
	if not account:
		frappe.throw(_("Account {0} is missing for {1}. Run bench migrate to create it.").format(name, company))
	return account


def purchase_invoice_for(name):
	wc = frappe.get_doc("Work Certificate", name)
	wc.check_permission("read")
	frappe.has_permission("Purchase Invoice", "create", throw=True)
	if wc.docstatus != 1:
		frappe.throw(_("Submit {0} first: only a certified amount is invoiced.").format(wc.name))
	if wc.purchase_invoice and frappe.db.get_value("Purchase Invoice", wc.purchase_invoice, "docstatus") < 2:
		frappe.throw(_("{0} is already invoiced on {1}.").format(wc.name, wc.purchase_invoice))
	company = frappe.db.get_value("Purchase Order", wc.subcontract_po, "company") if wc.subcontract_po else \
		frappe.db.get_value("Project", wc.project, "company")
	pi = frappe.new_doc("Purchase Invoice")
	pi.update({"supplier": wc.supplier, "company": company, "project": wc.project, "work_certificate": wc.name,
	           "bill_no": wc.certificate_no or wc.name, "bill_date": wc.period_to,
	           "remarks": _("Work certificate {0}, period {1} to {2}.").format(wc.name, wc.period_from or "", wc.period_to or "")})
	rates = []
	for row in wc.items:
		if not flt(row.this_period_qty):
			continue
		po_detail = frappe.db.get_value("Purchase Order Item", {"parent": wc.subcontract_po, "item_code": row.item_code}, "name") \
			if wc.subcontract_po else None
		pi.append("items", {"item_code": row.item_code, "qty": flt(row.this_period_qty), "project": wc.project, "wbs": wc.wbs,
		                    "cost_code": row.cost_code, "purchase_order": wc.subcontract_po if po_detail else None, "po_detail": po_detail,
		                    "description": _("{0}: {1} certified on {2}").format(row.item_code, flt(row.this_period_qty), wc.name)})
		rates.append(flt(row.rate))
	if not pi.items:
		frappe.throw(_("{0} certifies nothing this period.").format(wc.name))
	pi.run_method("set_missing_values")
	for row, rate in zip(pi.items, rates):
		row.rate = row.price_list_rate = rate
		row.discount_percentage = row.discount_amount = 0
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	for d in wc.deductions:
		pi.append("taxes", {"category": "Total", "add_deduct_tax": "Deduct", "charge_type": "Actual",
		                    "account_head": _account(company, BACK_CHARGES), "description": f"{_(d.deduction_type)}: {d.description}",
		                    "tax_amount": flt(d.amount), "wbs": d.wbs, "cost_code": d.cost_code, "cost_center": cost_center})
	pi.run_method("calculate_taxes_and_totals")
	pi.insert()
	wc.db_set("purchase_invoice", pi.name)
	wc.add_comment("Info", _("Invoiced: {0}").format(pi.name))
	return pi.name


def retention_on(pi):
	return flt(frappe.db.get_value("Work Certificate", pi.work_certificate, "total_retention")) if pi.get("work_certificate") else 0


def on_submit(doc, method=None):
	"""Move the certificate's retention from the invoice's payable to Retention Payable, on the supplier."""
	retention = retention_on(doc)
	if not retention:
		return
	wbs = frappe.db.get_value("Work Certificate", doc.work_certificate, "wbs")
	je = frappe.new_doc("Journal Entry")
	je.update({"voucher_type": "Journal Entry", "company": doc.company, "posting_date": doc.posting_date,
	           "user_remark": _("Retention held on {0} ({1}), released at the end of the defects liability period.").format(
	               doc.work_certificate, doc.name)})
	common = {"party_type": "Supplier", "party": doc.supplier, "project": doc.project, "wbs": wbs,
	          "cost_center": frappe.get_cached_value("Company", doc.company, "cost_center")}
	je.append("accounts", {**common, "account": doc.credit_to, "debit_in_account_currency": retention,
	                       "reference_type": "Purchase Invoice", "reference_name": doc.name})
	je.append("accounts", {**common, "account": _account(doc.company, RETENTION_ACCOUNT_NAME), "credit_in_account_currency": retention})
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	doc.db_set("retention_journal", je.name)


def before_cancel(doc, method=None):
	if doc.get("retention_journal") and frappe.db.get_value("Journal Entry", doc.retention_journal, "docstatus") == 1:
		je = frappe.get_doc("Journal Entry", doc.retention_journal)
		je.flags.ignore_permissions = True
		je.flags.ignore_links = True  # the invoice being cancelled links to it
		je.cancel()


def release_links(doc, method=None):
	"""A cancelled or deleted invoice frees its certificate."""
	for name in frappe.get_all("Work Certificate", filters={"purchase_invoice": doc.name}, pluck="name"):
		frappe.db.set_value("Work Certificate", name, "purchase_invoice", None, update_modified=False)
