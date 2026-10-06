# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""The number cards on the Finance & Accounting workspace.

Each card is a Custom number card calling one method here, and every method
takes its figure from the Finance & Accounting Overview's own calculations
(a3_constructa.api.finance_accounting_overview). The cards and the overview tab
therefore always agree: the user's default company only, in that company's
currency, through the user's permissions.

Document Type and Report cards could do neither. They sum a field across every
company, adding rupees to dollars, and carry one fixed currency.

A card the user cannot read shows "N/A". Clicking a card opens the list or
report behind its figure, narrowed to the same company.
"""

import frappe
from frappe.utils import getdate, today

from a3_constructa.api import finance_accounting_overview as overview
from a3_constructa.api.utils import default_company, default_currency

# Formatted in the default company's currency, which ERPNext's boot loads for
# every company.
MONEY = {"fieldtype": "Currency", "options": "Company:company:default_currency"}
PERCENT = {"fieldtype": "Percent"}


def _readable() -> set:
	return {dt for dt in overview.DOCTYPES if frappe.has_permission(dt, "read")}


def _card(value, df, route, route_options=None) -> dict:
	return {"value": value, **df, "route": route, "route_options": route_options}


def _company() -> dict:
	company = default_company()
	return {"company": company} if company else {}


def _invoices(doctype, party_field):
	return overview._open_invoices(doctype, party_field, _readable(), getdate(today()), default_currency())


@frappe.whitelist()
def total_receivable(filters=None) -> dict:
	rows = _invoices("Sales Invoice", "customer")
	return _card(
		None if rows is None else sum(row.amount for row in rows),
		MONEY,
		["List", "Sales Invoice"],
		overview._listed(overview.OPEN),
	)


@frappe.whitelist()
def overdue_receivable(filters=None) -> dict:
	rows = _invoices("Sales Invoice", "customer")
	now = getdate(today())
	return _card(
		None if rows is None else sum(row.amount for row in rows if row.due_date and row.days_late > 0),
		MONEY,
		["List", "Sales Invoice"],
		overview._listed({**overview.OPEN, "due_date": ["<", str(now)]}),
	)


@frappe.whitelist()
def total_payable(filters=None) -> dict:
	rows = _invoices("Purchase Invoice", "supplier")
	return _card(
		None if rows is None else sum(row.amount for row in rows),
		MONEY,
		["List", "Purchase Invoice"],
		overview._listed(overview.OPEN),
	)


@frappe.whitelist()
def cash_and_bank_balance(filters=None) -> dict:
	cash = overview._cash(_readable(), getdate(today()))
	return _card(
		None if cash["restricted"] else cash["total"],
		MONEY,
		["query-report", "Cash and Bank Balance"],
		_company(),
	)


@frappe.whitelist()
def committed_but_unbilled(filters=None) -> dict:
	"""Submitted purchase orders still open, less what has been invoiced."""
	readable = _readable()
	value = overview._unbilled("Purchase Order", "Purchase Order Item")[0] if "Purchase Order" in readable else None
	return _card(
		value,
		MONEY,
		["List", "Purchase Order"],
		overview._listed({"docstatus": 1, "status": ["not in", list(overview.ORDER_DONE)], "per_billed": ["<", 100]}),
	)


@frappe.whitelist()
def retention_held(filters=None) -> dict:
	"""The net balance on the retention payable accounts: held less released."""
	if not {"GL Entry", "Account"} <= _readable():
		return _card(None, MONEY, ["List", "GL Entry"])
	accounts = overview._accounts({"name": ["like", overview.RETENTION_ACCOUNT]})
	balances = overview._balances(accounts, {"posting_date": ["<=", today()]})
	return _card(
		# Credit balances are held amounts; 0.0 - x never gives -0.
		0.0 - sum(balances.values()),
		MONEY,
		["List", "GL Entry"],
		overview._listed({"account": ["like", overview.RETENTION_ACCOUNT], "is_cancelled": 0}),
	)


@frappe.whitelist()
def budget_utilisation(filters=None) -> dict:
	"""Actual plus committed, as a share of the whole cost-code budget."""
	readable = _readable()
	ordered = overview._unbilled("Purchase Order", "Purchase Order Item") if "Purchase Order" in readable else None
	budget = overview._budget(readable, ordered)
	return _card(
		None if budget["restricted"] else budget["percent"],
		PERCENT,
		["query-report", "Cost Code Wise Costing"],
		_company(),
	)
