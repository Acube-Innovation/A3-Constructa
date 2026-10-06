# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 1.3, 1.7, 9.9: cost code accounting on invoices, journals and claims.

A line that carries a cost code posts to the cost code's GL account and cost
centre, the way Stock Entry lines already do (overrides/stock_entry.py), so a
project's costs land under its own heads whoever keys the document. The WBS and
cost code themselves reach the GL Entry through the Accounting Dimensions set
up in setup/accounting_dimensions.py.

Only an Active cost code may be used on any document. A Purchase Invoice line
that came through a receipt is checked against its order: quantity against
what was received, rate against the order (three-way match). A mismatch is
flagged on the line and shown to the user; it does not stop the save.
"""

import frappe
from frappe import _
from frappe.utils import flt

# doctype -> (child table, account field, cost centre field) whose account follows the cost code
COST_CODE_LINES = {
	"Purchase Invoice": ("items", "expense_account", "cost_center"),
	"Journal Entry": ("accounts", "account", "cost_center"),
	"Expense Claim": ("expenses", "default_account", "cost_center"),
}


def validate_active_cost_codes(doc, method=None):
	"""Refuse an Inactive (or missing) cost code on the document or any of its lines."""
	used = {}
	if doc.meta.has_field("cost_code") and doc.get("cost_code"):
		used.setdefault(doc.cost_code, _("the document"))
	for table in doc.meta.get_table_fields():
		for row in doc.get(table.fieldname) or []:
			if row.get("cost_code"):
				used.setdefault(row.cost_code, _("row {0}").format(row.idx))
	if not used:
		return
	status = dict(frappe.get_all("Cost Code", filters={"name": ["in", list(used)]}, fields=["name", "status"], as_list=True))
	bad = [(code, where) for code, where in used.items() if status.get(code) != "Active"]
	if bad:
		frappe.throw(
			"<br>".join(
				_("{0}: cost code {1} is {2}.").format(where, frappe.bold(code), status.get(code) or _("missing")) for code, where in bad
			)
			+ "<br>" + _("Only Active cost codes can be used. Pick another cost code or reactivate this one."),
			title=_("Inactive cost code"),
		)


def apply_cost_code_accounting(doc, method=None):
	"""Point each line with a cost code at the cost code's account and cost centre.

	Runs after ERPNext's own validate, which fills the defaults, so the cost code
	wins (same reasoning as overrides/stock_entry.py). A stock item on a Purchase
	Invoice is left alone: its debit goes to Stock Received But Not Billed or to
	stock, and becomes a cost only when the material is issued to the works.
	"""
	table, account_field, cc_field = COST_CODE_LINES[doc.doctype]
	rows = [row for row in doc.get(table) or [] if row.get("cost_code")]
	if not rows:
		return
	codes = {
		c.name: c
		for c in frappe.get_all("Cost Code", filters={"name": ["in", list({r.cost_code for r in rows})]},
		                        fields=["name", "account", "cost_center"])
	}
	for row in rows:
		code = codes.get(row.cost_code)
		if not code:
			continue
		if doc.doctype == "Purchase Invoice" and is_stock_line(row):
			continue
		if code.account:
			company = frappe.get_cached_value("Account", code.account, "company")
			if company != doc.company:
				frappe.throw(_("Row {0}: cost code {1} posts to {2}, an account of {3}, not {4}.").format(
					row.idx, row.cost_code, code.account, company, doc.company))
			row.set(account_field, code.account)
		if code.cost_center:
			row.set(cc_field, code.cost_center)

	# ERPNext titles a new journal after its first account before the swap above,
	# so a title still naming the old account is set again.
	if doc.doctype == "Journal Entry" and doc.is_new() and hasattr(doc, "get_title"):
		doc.title = doc.get_title()


def is_stock_line(row):
	if row.get("is_fixed_asset"):
		return True
	return bool(row.get("item_code") and frappe.get_cached_value("Item", row.item_code, "is_stock_item"))


def check_three_way_match(doc, method=None):
	"""Purchase Invoice: flag lines whose qty differs from what was received, or
	whose rate differs from the order. Lines not from an order are left blank."""
	po_lines = {
		r.name: r
		for r in frappe.get_all("Purchase Order Item", filters={"name": ["in", [r.po_detail for r in doc.items if r.po_detail] or [""]]},
		                        fields=["name", "qty", "rate", "conversion_factor"])
	}
	pr_lines = {
		r.name: r
		for r in frappe.get_all("Purchase Receipt Item", filters={"name": ["in", [r.pr_detail for r in doc.items if r.pr_detail] or [""]]},
		                        fields=["name", "qty", "received_qty"])
	}
	flagged = []
	for row in doc.items:
		po = po_lines.get(row.po_detail)
		if not po:
			row.three_way_match = None
			continue
		expected_qty = flt(pr_lines[row.pr_detail].qty) if row.pr_detail in pr_lines else flt(po.qty)
		if doc.get("work_certificate") and row.pr_detail not in pr_lines:
			expected_qty = flt(row.qty)  # a subcontract is received by certificate: the certified quantity is what was received
		qty_off = abs(flt(row.qty) - expected_qty) > 0.0001
		rate_off = abs(flt(row.rate) - flt(po.rate)) > 0.005
		row.three_way_match = (
			"Qty and rate differ" if qty_off and rate_off else "Qty differs" if qty_off else "Rate differs" if rate_off else "Matched"
		)
		if qty_off or rate_off:
			parts = []
			if qty_off:
				parts.append(_("qty {0}, {1} {2}").format(f"{flt(row.qty):g}", _("received") if row.pr_detail in pr_lines else _("ordered"), f"{expected_qty:g}"))
			if rate_off:
				parts.append(_("rate {0}, ordered at {1}").format(f"{flt(row.rate):g}", f"{flt(po.rate):g}"))
			flagged.append(_("Row {0} ({1}): {2}").format(row.idx, row.item_code, "; ".join(parts)))
	if flagged and not doc.flags.silent_three_way:
		frappe.msgprint("<br>".join(flagged), title=_("Three-way match: check these lines"), indicator="orange")
