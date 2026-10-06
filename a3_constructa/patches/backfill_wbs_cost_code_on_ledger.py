# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01D: fill WBS and cost code on lines and GL entries posted before they were
Accounting Dimensions. Nothing is reposted and no amount changes.

Lines take the values of the line they were made from: a Purchase Receipt line
from its order line, a Purchase Invoice line from its receipt line (or order
line), a Sales Invoice line from its sales order line.

A GL entry carries no reference to the line that made it, and ERPNext merges
entries that share an account. So a GL entry is stamped only when every line of
its voucher that could have posted to that account has the same WBS and cost
code; anything ambiguous is left blank and counted.
"""

import frappe

from a3_constructa.setup import accounting_dimensions

FIELDS = ("wbs", "cost_code")

# (line doctype, link to source line, source line doctype)
LINE_SOURCES = [
	("Purchase Receipt Item", "purchase_order_item", "Purchase Order Item"),
	("Purchase Invoice Item", "pr_detail", "Purchase Receipt Item"),
	("Purchase Invoice Item", "po_detail", "Purchase Order Item"),
	("Sales Invoice Item", "so_detail", "Sales Order Item"),
]

# voucher type -> (line doctype, account fields on the line, warehouse fields on the line)
VOUCHERS = {
	"Purchase Invoice": ("Purchase Invoice Item", ("expense_account",), ("warehouse",)),
	"Purchase Receipt": ("Purchase Receipt Item", ("expense_account",), ("warehouse",)),
	"Stock Entry": ("Stock Entry Detail", ("expense_account",), ("s_warehouse", "t_warehouse")),
	"Journal Entry": ("Journal Entry Account", ("account",), ()),
	"Expense Claim": ("Expense Claim Detail", ("default_account",), ()),
	"Sales Invoice": ("Sales Invoice Item", ("income_account",), ("warehouse",)),
}


def execute():
	accounting_dimensions.sync()
	fill_lines()
	stamped, ambiguous = fill_gl()
	print(f"P-01D backfill: {stamped} GL entries stamped with WBS / cost code, {ambiguous} left blank (lines disagree)")


def fill_lines():
	for line_dt, link, source_dt in LINE_SOURCES:
		if not all(frappe.db.has_column(dt, f) for dt in (line_dt, source_dt) for f in FIELDS):
			continue
		for f in FIELDS:
			frappe.db.sql(
				f"""
				update `tab{line_dt}` line
				inner join `tab{source_dt}` src on src.name = line.{link}
				set line.{f} = src.{f}
				where ifnull(line.{f}, '') = '' and ifnull(src.{f}, '') != ''
				"""
			)


def fill_gl():
	stamped = ambiguous = 0
	for voucher_type, (line_dt, account_fields, warehouse_fields) in VOUCHERS.items():
		if not frappe.db.has_column(line_dt, "wbs"):
			continue
		vouchers = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": voucher_type, "is_cancelled": 0, "wbs": ["is", "not set"], "cost_code": ["is", "not set"]},
			pluck="voucher_no",
			distinct=True,
		)
		for voucher_no in vouchers:
			by_account = combos_by_account(voucher_type, voucher_no, line_dt, account_fields, warehouse_fields)
			if not by_account:
				continue
			for gle in frappe.get_all(
				"GL Entry",
				filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "is_cancelled": 0,
				         "party": ["is", "not set"], "wbs": ["is", "not set"], "cost_code": ["is", "not set"]},
				fields=["name", "account"],
			):
				combos = by_account.get(gle.account)
				if not combos:
					continue
				if len(combos) == 1:
					wbs, cost_code = next(iter(combos))
					frappe.db.set_value("GL Entry", gle.name, {"wbs": wbs, "cost_code": cost_code}, update_modified=False)
					stamped += 1
				else:
					ambiguous += 1
	return stamped, ambiguous


def combos_by_account(voucher_type, voucher_no, line_dt, account_fields, warehouse_fields):
	"""For each account the voucher's lines could post to, the distinct (wbs, cost code) they carry."""
	company = frappe.db.get_value(voucher_type, voucher_no, "company")
	fields = list(FIELDS) + [f for f in account_fields + warehouse_fields if frappe.db.has_column(line_dt, f)]
	lines = frappe.get_all(line_dt, filters={"parent": voucher_no, "parenttype": voucher_type}, fields=fields)
	if not any(l.wbs or l.cost_code for l in lines):
		return {}
	defaults = frappe.get_cached_value("Company", company, ["default_inventory_account", "stock_received_but_not_billed"], as_dict=True)
	out = {}
	for line in lines:
		accounts = {line.get(f) for f in account_fields if line.get(f)}
		for wf in warehouse_fields:
			if line.get(wf):
				accounts.add(frappe.get_cached_value("Warehouse", line.get(wf), "account") or defaults.default_inventory_account)
				if voucher_type == "Purchase Receipt" or (voucher_type == "Purchase Invoice"):
					accounts.add(defaults.stock_received_but_not_billed)
		combo = (line.wbs or None, line.cost_code or None)
		for account in accounts:
			if account:
				out.setdefault(account, set()).add(combo)
	# An account only lines without a WBS or cost code post to has nothing to stamp.
	out = {account: combos for account, combos in out.items() if combos != {(None, None)}}
	return out
