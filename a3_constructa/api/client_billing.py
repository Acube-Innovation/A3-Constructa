# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Client billing documents - catalogue 4.3, 4.4, 4.5.

- The invoice of a certified IPC: a line per WBS (with project, WBS and cost
  code), VAT on the certified gross, then two deductions as tax rows: retention
  to Retention Receivable and the advance recovered against Advances from
  Customers. The receivable is the net due plus VAT.
- The advance invoice: billed against the client's bank guarantee and credited
  to Advances from Customers, so the IPCs recover it.
- Retention release: the first half at practical completion, the second at the
  end of the defects liability period, each an invoice against Retention
  Receivable.
- From the agreed final account (catalogue 4.7): the final invoice for the balance
  due, recovering what is left of the advance, and the release of whatever
  retention is still held once the defects liability period is over.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, today

from a3_constructa.api.award_handover import contract_item
from a3_constructa.overrides.sales_order import wbs_for
from a3_constructa.setup.install_defaults import CUSTOMER_ADVANCES, RETENTION_RECEIVABLE, contract_account


def _account(company, name):
	account = contract_account(company, name)
	if not account:
		frappe.throw(_("Account {0} is missing for {1}. Run bench migrate to create it.").format(name, company))
	return account


def _new_invoice(a, remarks, **extra):
	settings = frappe.get_cached_doc("A3 Constructa Settings")
	si = frappe.new_doc("Sales Invoice")
	si.update({"customer": a.customer, "company": a.company, "currency": a.currency, "project": a.project,
	           "awarded_quotation": a.name, "posting_date": today(), "set_posting_time": 0,
	           "payment_terms_template": settings.contract_payment_terms, "remarks": remarks, **extra})
	return si


def _finish(si, rates, vat=True):
	"""Fill ERPNext's defaults, keep the agreed rates, add VAT if asked, insert as a draft."""
	si.run_method("set_missing_values")
	for row, rate in zip(si.items, rates):
		row.rate = row.price_list_rate = rate
		row.discount_percentage = row.discount_amount = 0
	si.set("taxes", [t for t in si.taxes if t.charge_type == "Actual" and t.get("a3_deduction")])
	settings = frappe.get_cached_doc("A3 Constructa Settings")
	if vat and settings.contract_taxes and frappe.db.get_value("Sales Taxes and Charges Template", settings.contract_taxes, "company") == si.company:
		deductions = list(si.taxes)
		si.taxes_and_charges = settings.contract_taxes
		si.set("taxes", [])
		si.append_taxes_from_master("Sales Taxes and Charges Template")
		for d in deductions:
			si.append("taxes", d)
	else:
		si.taxes_and_charges = None
	si.run_method("calculate_taxes_and_totals")
	si.insert()
	return si


# ---------------------------------------------------------------- IPC invoice

def invoice_for_ipc(ipc_name):
	ipc = frappe.get_doc("Client IPC", ipc_name)
	ipc.check_permission("read")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	if ipc.docstatus != 1 or ipc.status != "Certified" or ipc.sales_invoice:
		frappe.throw(_("Only a certified IPC without an invoice can be invoiced; {0} is {1}.").format(ipc.name, _(ipc.status)))
	a = frappe.get_doc("Awarded Quotation", ipc.awarded_quotation)
	si = _new_invoice(a, _("IPC {0} for {1}, period {2} to {3}.").format(ipc.ipc_no, a.name, ipc.period_from, ipc.period_to),
	                  client_ipc=ipc.name)
	# One line per WBS (and cost code), as the certificate's work splits.
	groups = {}
	for row in ipc.items:
		if not flt(row.this_period_amount):
			continue
		key = (row.wbs, row.cost_code)
		groups.setdefault(key, {"amount": 0.0, "refs": []})
		groups[key]["amount"] += flt(row.this_period_amount)
		groups[key]["refs"].append(row.line_ref or row.description[:20])
	rates = []
	for (wbs, cost_code), g in groups.items():
		head = frappe.db.get_value("WBS", wbs, "cost_head") if wbs else None
		si.append("items", {"item_code": contract_item(head), "qty": 1, "project": a.project, "wbs": wbs, "cost_code": cost_code,
		                    "description": _("IPC {0}: work certified on {1} ({2})").format(ipc.ipc_no, wbs or _("the project"), ", ".join(g["refs"]))})
		rates.append(flt(g["amount"], 2))
	if not groups and not flt(ipc.materials_on_site):
		frappe.throw(_("{0} certifies nothing this period, so there is nothing to invoice.").format(ipc.name))
	if flt(ipc.materials_on_site):
		root = wbs_for(a.project, a.name, frappe._dict(wbs=None, boq_ref=None, cost_head=None)) if a.project else None
		si.append("items", {"item_code": contract_item(None), "qty": 1, "project": a.project, "wbs": root,
		                    "description": _("IPC {0}: materials on site").format(ipc.ipc_no)})
		rates.append(flt(ipc.materials_on_site))
	for amount, account, label in ((ipc.retention_this_period, RETENTION_RECEIVABLE, _("Retention {0}%").format(flt(ipc.retention_percent))),
	                               (ipc.advance_recovered_this_period, CUSTOMER_ADVANCES, _("Advance recovery {0}%").format(flt(ipc.advance_recovery_percent)))):
		if flt(amount):
			row = si.append("taxes", {"charge_type": "Actual", "account_head": _account(a.company, account), "description": label,
			                          "tax_amount": -flt(amount), "cost_center": frappe.get_cached_value("Company", a.company, "cost_center")})
			row.a3_deduction = 1
	si = _finish(si, rates)
	ipc.db_set({"sales_invoice": si.name, "status": "Invoiced"})
	ipc.add_comment("Info", _("Invoiced: {0}").format(si.name))
	return si.name


# ---------------------------------------------------------------- advance

@frappe.whitelist()
def make_advance_invoice(award: str, bank_guarantee: str, amount: float | None = None) -> str:
	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("read")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	bg = frappe.db.get_value("Bank Guarantee", bank_guarantee, ["docstatus", "end_date", "customer", "amount"], as_dict=True)
	if not bg or bg.docstatus != 1:
		frappe.throw(_("The advance needs a submitted bank guarantee from the client's bank."))
	if bg.end_date and getdate(bg.end_date) < getdate(today()):
		frappe.throw(_("Bank guarantee {0} expired on {1}.").format(bank_guarantee, bg.end_date))
	from a3_constructa.a3_constructa.doctype.client_ipc.client_ipc import advance_billed

	# The advance is a share of the contract as awarded; variations do not add to it.
	allowed = flt(flt(a.contract_value) * flt(a.advance_percent) / 100, 2) - advance_billed(a.name)
	amount = flt(amount) or allowed
	if amount <= 0 or amount > allowed + 0.005:
		frappe.throw(_("The advance can be at most {0} ({1}% of the contract, less advances already billed).").format(
			frappe.format(max(allowed, 0), {"fieldtype": "Currency", "options": "currency"}, doc=a), flt(a.advance_percent)))
	si = _new_invoice(a, _("Advance payment, {0}% of {1}, against bank guarantee {2}.").format(flt(a.advance_percent), a.name, bank_guarantee),
	                  is_advance_invoice=1, bank_guarantee=bank_guarantee)
	si.append("items", {"item_code": contract_item(None), "qty": 1, "income_account": _account(a.company, CUSTOMER_ADVANCES),
	                    "description": _("Advance payment on {0}").format(a.title)})
	si = _finish(si, [amount], vat=False)
	for row in si.items:  # set_missing_values would put the item's income account back
		row.income_account = _account(a.company, CUSTOMER_ADVANCES)
	si.save()
	return si.name


# ---------------------------------------------------------------- retention release

def retention_held(award):
	return flt(frappe.db.sql("""select sum(retention_this_period) from `tabClient IPC`
		where awarded_quotation = %s and docstatus = 1""", award)[0][0])


def release_due(a, half):
	"""Why a release is not yet possible, or None."""
	if not a.practical_completion_date:
		return _("Enter the practical completion date first.")
	if half == 2:
		if not a.retention_release_1:
			return _("Release the first half first.")
		end = add_months(a.practical_completion_date, int(a.defects_liability_months or 0))
		if getdate(end) > getdate(today()):
			return _("The defects liability period ends on {0}.").format(frappe.format(end, {"fieldtype": "Date"}))
	if a.get(f"retention_release_{half}"):
		return _("Already released: {0}.").format(a.get(f"retention_release_{half}"))
	return None


@frappe.whitelist()
def release_retention(award: str, half: int) -> str:
	half = int(half)
	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("read")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	reason = release_due(a, half)
	if reason:
		frappe.throw(reason, title=_("Retention release"))
	held = retention_held(a.name)
	first = flt(frappe.db.get_value("Sales Invoice", a.retention_release_1, "net_total")) if a.retention_release_1 else 0
	amount = flt(held / 2, 2) if half == 1 else flt(held - first, 2)
	if amount <= 0:
		frappe.throw(_("No retention is held on {0}.").format(a.name))
	label = _("first half, at practical completion") if half == 1 else _("second half, at the end of the defects liability period")
	si = _new_invoice(a, _("Retention release, {0}: {1}.").format(label, a.name), is_retention_release=1)
	si.append("items", {"item_code": contract_item(None), "qty": 1, "income_account": _account(a.company, RETENTION_RECEIVABLE),
	                    "description": _("Release of retention, {0}").format(label)})
	si = _finish(si, [amount], vat=False)
	for row in si.items:
		row.income_account = _account(a.company, RETENTION_RECEIVABLE)
	si.save()
	frappe.db.set_value("Awarded Quotation", a.name, f"retention_release_{half}", si.name, update_modified=False)
	return si.name


# ---------------------------------------------------------------- final account

def _agreed_account(name):
	fa = frappe.get_doc("Final Account", name)
	fa.check_permission("read")
	frappe.has_permission("Sales Invoice", "create", throw=True)
	if fa.docstatus != 1:
		frappe.throw(_("Agree (submit) final account {0} first.").format(fa.name))
	fa.calculate()
	return fa, frappe.get_doc("Awarded Quotation", fa.awarded_quotation)


def final_invoice(name):
	"""The balance due on the agreed final account, plus VAT, less the advance still to recover."""
	fa, a = _agreed_account(name)
	if fa.final_invoice and frappe.db.get_value("Sales Invoice", fa.final_invoice, "docstatus") < 2:
		frappe.throw(_("Final invoice {0} already exists.").format(fa.final_invoice))
	balance = flt(fa.balance_due, 2)
	if balance <= 0:
		frappe.throw(_("Nothing is left to bill: certified to date {0} already reaches the final contract sum of {1}. A credit note settles an over-payment.").format(
			frappe.format(fa.certified_to_date, {"fieldtype": "Currency", "options": "currency"}, doc=fa),
			frappe.format(fa.final_contract_sum, {"fieldtype": "Currency", "options": "currency"}, doc=fa)), title=_("Final invoice"))
	root = wbs_for(a.project, a.name, frappe._dict(wbs=None, boq_ref=None, cost_head=None)) if a.project else None
	si = _new_invoice(a, _("Final account {0} for {1}: balance of the final contract sum.").format(fa.name, a.name), final_account=fa.name)
	si.append("items", {"item_code": contract_item(None), "qty": 1, "project": a.project, "wbs": root,
	                    "description": _("Final account {0}: final contract sum {1} less {2} certified to date").format(
	                        fa.name, frappe.format(fa.final_contract_sum, {"fieldtype": "Currency", "options": "currency"}, doc=fa),
	                        frappe.format(fa.certified_to_date, {"fieldtype": "Currency", "options": "currency"}, doc=fa))})
	recovery = min(max(flt(fa.advance_balance), 0), balance)
	if recovery:
		row = si.append("taxes", {"charge_type": "Actual", "account_head": _account(a.company, CUSTOMER_ADVANCES),
		                          "description": _("Advance still to recover"), "tax_amount": -recovery,
		                          "cost_center": frappe.get_cached_value("Company", a.company, "cost_center")})
		row.a3_deduction = 1
	si = _finish(si, [balance])
	fa.db_set("final_invoice", si.name)
	fa.add_comment("Info", _("Final invoice: {0}").format(si.name))
	return si.name


def release_remaining_retention(name):
	"""Whatever retention is still held, released once the defects liability period is over."""
	fa, a = _agreed_account(name)
	if not a.practical_completion_date:
		frappe.throw(_("Enter the practical completion date on {0} first.").format(a.name), title=_("Retention release"))
	end = add_months(a.practical_completion_date, int(a.defects_liability_months or 0))
	if getdate(end) > getdate(today()):
		frappe.throw(_("The defects liability period ends on {0}; the remaining retention is released then.").format(
			frappe.format(end, {"fieldtype": "Date"})), title=_("Retention release"))
	amount = flt(flt(fa.retention_held) - flt(fa.retention_released), 2)
	if amount <= 0:
		frappe.throw(_("No retention is left to release on {0}.").format(a.name), title=_("Retention release"))
	si = _new_invoice(a, _("Release of the remaining retention on {0}, final account {1}.").format(a.name, fa.name),
	                  is_retention_release=1, final_account=fa.name)
	si.append("items", {"item_code": contract_item(None), "qty": 1, "income_account": _account(a.company, RETENTION_RECEIVABLE),
	                    "description": _("Release of the remaining retention, final account {0}").format(fa.name)})
	si = _finish(si, [amount], vat=False)
	for row in si.items:
		row.income_account = _account(a.company, RETENTION_RECEIVABLE)
	si.save()
	fa.db_set("retention_release_invoice", si.name)
	# The award's two halves are both settled by this release.
	for half in (1, 2):
		if not a.get(f"retention_release_{half}"):
			frappe.db.set_value("Awarded Quotation", a.name, f"retention_release_{half}", si.name, update_modified=False)
	fa.add_comment("Info", _("Remaining retention released: {0}").format(si.name))
	return si.name


# ---------------------------------------------------------------- invoice cancelled

def release_links(doc, method=None):
	"""A cancelled or deleted invoice frees its IPC, milestone, retention release or final account."""
	from a3_constructa.api.milestone_billing import release_milestone

	release_milestone(doc, method)
	for name in frappe.get_all("Client IPC", filters={"sales_invoice": doc.name, "opening_invoice": ["is", "not set"]}, pluck="name"):
		frappe.db.set_value("Client IPC", name, {"sales_invoice": None, "status": "Certified"})
	for half in (1, 2):
		for name in frappe.get_all("Awarded Quotation", filters={f"retention_release_{half}": doc.name}, pluck="name"):
			frappe.db.set_value("Awarded Quotation", name, f"retention_release_{half}", None, update_modified=False)
	for field in ("final_invoice", "retention_release_invoice"):
		for name in frappe.get_all("Final Account", filters={field: doc.name}, pluck="name"):
			frappe.db.set_value("Final Account", name, field, None, update_modified=False)
