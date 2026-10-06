# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Finance & Accounting Overview" tab of the Finance & Accounting workspace.

Same contract as the other workspace overviews: one call, every figure through
`frappe.get_list` so the caller's permissions apply, and a section the caller
cannot read comes back `restricted`. Everything is the user's default company
(a3_constructa.api.utils), and money is that company's currency.

What is owed either way comes from submitted invoices with something left to
pay, as the Total Receivable and Total Payable number cards count them. An
invoice's `outstanding_amount` is in its party account's currency, so one
booked to a foreign-currency party account is converted at the invoice's own
rate. Ageing is days past the due date.

Ledger figures (cash and bank, profit, retention) are GL Entry debits and
credits, which are always in the company currency. Cash and bank are the leaf
accounts of type Bank or Cash, as the Cash and Bank Balance report reads them;
retention is the balance of the "Retention Payable" accounts the Retention Held
card and the Working Capital report read.

Commitments follow Cost Code Wise Costing: a submitted purchase order commits
its value less what has been invoiced against it, until it is closed. (Budget
vs Commitment, behind the "Committed but Unbilled" card, sums whole order
values instead.) Budget used is Cost Code Wise Costing's actual plus committed
over the WBS Allocation budget, taken across all cost codes together rather
than as an average of each code's percentage.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, flt, get_first_day, getdate, now_datetime, today

from a3_constructa.api.utils import company_projects, default_company, default_currency

DOCTYPES = (
	"Sales Invoice",
	"Purchase Invoice",
	"GL Entry",
	"Account",
	"Purchase Order",
	"Sales Order",
	"Purchase Receipt",
	"Journal Entry",
	"Bank Transaction",
	"Project",
	"WBS Allocation",
	"Stock Entry",
)

OPEN = {"docstatus": 1, "outstanding_amount": [">", 0]}
CASH_AND_BANK = ("Bank", "Cash")
RETENTION_ACCOUNT = "Retention Payable%"
# Orders that still commit money: a closed one has released what it did not bill.
ORDER_DONE = ("Closed", "Completed")

AGEING = ((1, 30), (31, 60), (61, 90), (91, None))
LONG_OVERDUE_DAYS = 90
DUE_SOON_DAYS = 30
UNBILLED_RECEIPT_DAYS = 30
TREND_MONTHS = 12
TOP_PARTIES = 5
TOP_ACCOUNTS = 4
DUE_LIST = 8
PROJECT_LIST = 6


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	currency = default_currency()
	readable = {dt for dt in DOCTYPES if frappe.has_permission(dt, "read")}

	sales = _open_invoices("Sales Invoice", "customer", readable, now, currency)
	purchases = _open_invoices("Purchase Invoice", "supplier", readable, now, currency)
	ordered = _unbilled("Purchase Order", "Purchase Order Item") if "Purchase Order" in readable else None

	return {
		"generated_at": now_datetime(),
		"currency": currency,
		"cash": _cash(readable, now),
		"receivable": _ledger("Sales Invoice", "customer", sales, now),
		"payable": _ledger("Purchase Invoice", "supplier", purchases, now),
		"due": _due(sales, purchases, now),
		"profit": _profit(readable, now),
		"flow": _flow(readable, now),
		"commitments": _commitments(readable, now, ordered),
		"budget": _budget(readable, ordered),
		"projects": _projects(readable),
		"health": _health(readable, now),
	}


def _scoped(doctype, filters=None):
	"""`filters` narrowed to the default company, as a list of conditions."""
	if isinstance(filters, dict):
		conditions = [[doctype, field, *(value if isinstance(value, list) else ["=", value])] for field, value in filters.items()]
	else:
		conditions = list(filters or [])
	company = default_company()
	if company:
		if frappe.get_meta(doctype).has_field("company"):
			conditions.append([doctype, "company", "=", company])
		elif frappe.get_meta(doctype).has_field("project"):
			conditions.append([doctype, "project", "in", company_projects(company) or [""]])
	return conditions


def _listed(filters: dict) -> dict:
	"""List-view filters for a link: `filters` plus the company, so the list
	opened shows exactly the records counted here."""
	company = default_company()
	return {**filters, "company": company} if company else dict(filters)


def _count(doctype, filters=None) -> int:
	return frappe.get_list(doctype, filters=_scoped(doctype, filters), fields=["count(name) as n"])[0].n


def _top(rows, limit, measure="count") -> list[dict]:
	"""The largest `limit` groups, the rest folded into one "Other" row."""
	rows = sorted(rows, key=lambda row: -flt(row[measure]))
	top = rows[:limit]
	rest = rows[limit:]
	if rest:
		top.append(
			{
				"label": _("Other"),
				"value": None,
				"count": sum(row["count"] for row in rest),
				"amount": sum(flt(row.get("amount")) for row in rest),
				"other": True,
			}
		)
	return top


def _accounts(filters: dict) -> list[str]:
	"""Leaf accounts of the default company matching `filters`."""
	return frappe.get_list(
		"Account",
		filters=_scoped("Account", {**filters, "is_group": 0}),
		pluck="name",
		limit_page_length=0,
	)


def _balances(accounts: list[str], filters: dict) -> dict:
	"""Debit less credit per account, from GL entries matching `filters`."""
	if not accounts:
		return {}
	return {
		row.account: flt(row.debit) - flt(row.credit)
		for row in frappe.get_list(
			"GL Entry",
			filters=_scoped("GL Entry", {**filters, "is_cancelled": 0, "account": ["in", accounts]}),
			fields=["account", "sum(debit) as debit", "sum(credit) as credit"],
			group_by="account",
		)
	}


# ---------------------------------------------------------------- sections


def _cash(readable, now) -> dict:
	if not {"GL Entry", "Account"} <= readable:
		return {"restricted": True}

	accounts = frappe.get_list(
		"Account",
		filters=_scoped("Account", {"account_type": ["in", list(CASH_AND_BANK)], "is_group": 0}),
		fields=["name", "account_name", "account_type"],
		limit_page_length=0,
	)
	# A balance is as at today, never counting entries dated into the future.
	balances = _balances([row.name for row in accounts], {"posting_date": ["<=", str(now)]})
	rows = sorted(
		(
			{"name": row.name, "label": row.account_name, "type": row.account_type, "balance": balances.get(row.name, 0.0)}
			for row in accounts
		),
		key=lambda row: -abs(row["balance"]),
	)
	shown = [row for row in rows if row["balance"]][:TOP_ACCOUNTS]
	rest = [row for row in rows if row["balance"] and row not in shown]

	return {
		"restricted": False,
		"total": sum(row["balance"] for row in rows),
		"bank_count": sum(1 for row in rows if row["type"] == "Bank"),
		"cash_count": sum(1 for row in rows if row["type"] == "Cash"),
		"accounts": shown,
		"other_count": len(rest),
		"other_balance": sum(row["balance"] for row in rest),
		"as_on": now,
	}


def _open_invoices(doctype, party_field, readable, now, currency):
	"""Submitted invoices with something left to pay, the amount in company currency."""
	if doctype not in readable:
		return None
	rows = frappe.get_list(
		doctype,
		filters=_scoped(doctype, OPEN),
		fields=[
			"name",
			f"{party_field} as party",
			f"{party_field}_name as party_name",
			"due_date",
			"party_account_currency",
			"conversion_rate",
			"outstanding_amount",
		],
		order_by="due_date asc, name asc",
		limit_page_length=0,
	)
	for row in rows:
		foreign = row.party_account_currency and row.party_account_currency != currency
		row.amount = flt(row.outstanding_amount) * (flt(row.conversion_rate) or 1) if foreign else flt(row.outstanding_amount)
		row.days_late = date_diff(now, row.due_date) if row.due_date else 0
	return rows


def _ledger(doctype, party_field, rows, now) -> dict:
	"""What is owed on one side: totals, ageing and the largest parties."""
	if rows is None:
		return {"restricted": True}

	def bucket(label, value, members):
		return {"label": label, "value": value, "count": len(members), "amount": sum(row.amount for row in members)}

	ageing = [bucket(_("Not yet due"), [">=", str(now)], [row for row in rows if row.due_date and row.days_late <= 0])]
	for low, high in AGEING:
		if high is None:
			label = _("Over {0} days").format(low - 1)
			value = ["<", str(add_days(now, -(low - 1)))]
			members = [row for row in rows if row.due_date and row.days_late >= low]
		else:
			label = _("{0}–{1} days").format(low, high)
			value = ["between", [str(add_days(now, -high)), str(add_days(now, -low))]]
			members = [row for row in rows if row.due_date and low <= row.days_late <= high]
		ageing.append(bucket(label, value, members))
	undated = [row for row in rows if not row.due_date]
	if undated:
		ageing.append(bucket(_("No due date"), None, undated))

	parties = {}
	for row in rows:
		party = parties.setdefault(row.party, {"label": row.party_name or row.party, "value": row.party, "count": 0, "amount": 0.0})
		party["count"] += 1
		party["amount"] += row.amount

	overdue = [row for row in rows if row.due_date and row.days_late > 0]
	return {
		"restricted": False,
		"doctype": doctype,
		"field": party_field,
		"filters": _listed(OPEN),
		"total": sum(row.amount for row in rows),
		"count": len(rows),
		"overdue": sum(row.amount for row in overdue),
		"overdue_count": len(overdue),
		"party_count": len(parties),
		"ageing": ageing,
		"by_party": _top(list(parties.values()), TOP_PARTIES, measure="amount"),
	}


def _due(sales, purchases, now) -> dict:
	"""Unpaid invoices either way: the overdue ones, then those due within DUE_SOON_DAYS."""
	if sales is None and purchases is None:
		return {"restricted": True}
	horizon = add_days(now, DUE_SOON_DAYS)
	rows = [
		{
			"doctype": doctype,
			"name": row.name,
			"party": row.party_name or row.party,
			"due_date": row.due_date,
			"days_late": row.days_late,
			"amount": row.amount,
		}
		for doctype, found in (("Sales Invoice", sales), ("Purchase Invoice", purchases))
		for row in found or []
		if row.due_date and getdate(row.due_date) <= horizon
	]
	rows.sort(key=lambda row: (getdate(row["due_date"]), -row["amount"]))
	return {
		"restricted": False,
		"partial": sales is None or purchases is None,
		"rows": rows[:DUE_LIST],
		"more": max(len(rows) - DUE_LIST, 0),
	}


def _profit(readable, now) -> dict:
	"""Income less expenses for the fiscal year so far, closing entries left out."""
	if not {"GL Entry", "Account"} <= readable:
		return {"restricted": True}
	from erpnext.accounts.utils import get_fiscal_year

	found = get_fiscal_year(now, company=default_company(), as_dict=True, boolean=True)
	if not found:
		return {"restricted": False, "fiscal_year": None}
	year = found[0]

	period = {
		"posting_date": ["between", [str(year.year_start_date), str(now)]],
		"voucher_type": ["!=", "Period Closing Voucher"],
	}
	income = -sum(_balances(_accounts({"root_type": "Income"}), period).values())
	expense = sum(_balances(_accounts({"root_type": "Expense"}), period).values())
	return {
		"restricted": False,
		"fiscal_year": year.name,
		"from_date": year.year_start_date,
		"income": income,
		"expense": expense,
		"net": income - expense,
	}


def _flow(readable, now) -> dict:
	"""Money into and out of the bank and cash accounts, month by month."""
	if not {"GL Entry", "Account"} <= readable:
		return {"restricted": True}
	first = getdate(get_first_day(add_months(now, -(TREND_MONTHS - 1))))
	months = [getdate(add_months(first, i)) for i in range(TREND_MONTHS)]
	found = {}
	accounts = _accounts({"account_type": ["in", list(CASH_AND_BANK)]})
	if accounts:
		for row in frappe.get_list(
			"GL Entry",
			filters=_scoped(
				"GL Entry",
				{
					"is_cancelled": 0,
					"account": ["in", accounts],
					"posting_date": ["between", [str(first), str(now)]],
				},
			),
			fields=["date_format(posting_date, '%Y-%m') as month", "sum(debit) as money_in", "sum(credit) as money_out"],
			group_by="month",
			order_by="month asc",
		):
			found[row.month] = row
	trend = []
	for month in months:
		key = month.strftime("%Y-%m")
		row = found.get(key) or {}
		trend.append(
			{
				"month": key,
				"label": month.strftime("%b %Y"),
				"short": month.strftime("%b"),
				"money_in": flt(row.get("money_in")),
				"money_out": flt(row.get("money_out")),
			}
		)
	return {"restricted": False, "trend": trend}


def _unbilled(doctype, child) -> tuple[float, int, dict]:
	"""Submitted orders still open: their value less what has been invoiced.

	Returns the total, the number of orders with something left, and the same
	amount per cost code (purchase orders only)."""
	has_code = doctype == "Purchase Order"
	rows = frappe.get_list(
		doctype,
		filters=_scoped(
			doctype,
			[
				[doctype, "docstatus", "=", 1],
				[doctype, "status", "not in", list(ORDER_DONE)],
				[child, "name", "is", "set"],
			],
		),
		fields=[
			"name",
			"conversion_rate",
			f"`tab{child}`.base_amount as base_amount",
			f"`tab{child}`.billed_amt as billed_amt",
			*([f"`tab{child}`.cost_code as cost_code"] if has_code else []),
		],
		limit_page_length=0,
	)
	total, orders, by_code = 0.0, set(), {}
	for row in rows:
		# billed_amt is in the order's currency; base_amount in the company's.
		left = max(flt(row.base_amount) - flt(row.billed_amt) * (flt(row.conversion_rate) or 1), 0)
		if left > 0.005:
			total += left
			orders.add(row.name)
			if has_code and row.cost_code:
				by_code[row.cost_code] = by_code.get(row.cost_code, 0) + left
	return total, len(orders), by_code


def _commitments(readable, now, ordered) -> dict:
	result = {}

	if ordered is not None:
		total, orders, _by_code = ordered
		result["committed"] = {"restricted": False, "amount": total, "count": orders}
	else:
		result["committed"] = {"restricted": True}

	if "Sales Order" in readable:
		total, orders, _by_code = _unbilled("Sales Order", "Sales Order Item")
		result["order_book"] = {"restricted": False, "amount": total, "count": orders}
	else:
		result["order_book"] = {"restricted": True}

	if {"GL Entry", "Account"} <= readable:
		accounts = _accounts({"name": ["like", RETENTION_ACCOUNT]})
		held = -sum(_balances(accounts, {"posting_date": ["<=", str(now)]}).values())
		result["retention"] = {"restricted": False, "amount": held, "accounts": len(accounts)}
	else:
		result["retention"] = {"restricted": True}

	return result


def _budget(readable, ordered) -> dict:
	"""Cost Code Wise Costing's totals: budget, actual and committed."""
	if ordered is None or not {"WBS Allocation", "GL Entry", "Stock Entry"} <= readable:
		return {"restricted": True}

	budget = flt(
		frappe.get_list(
			"WBS Allocation",
			filters=_scoped(
				"WBS Allocation",
				[["WBS Allocation", "docstatus", "<", 2], ["WBS Allocation Item", "cost_code", "is", "set"]],
			),
			fields=["sum(`tabWBS Allocation Item`.allocated_amount) as amount"],
		)[0].amount
	)

	ledger = frappe.get_list(
		"GL Entry",
		filters=_scoped("GL Entry", {"is_cancelled": 0, "cost_code": ["is", "set"]}),
		fields=["sum(debit) as debit", "sum(credit) as credit"],
	)[0]
	issued = frappe.get_list(
		"Stock Entry",
		filters=_scoped(
			"Stock Entry",
			[
				["Stock Entry", "docstatus", "=", 1],
				["Stock Entry", "purpose", "=", "Material Issue"],
				["Stock Entry Detail", "cost_code", "is", "set"],
			],
		),
		fields=["sum(`tabStock Entry Detail`.amount) as amount"],
	)[0]
	actual = flt(ledger.debit) - flt(ledger.credit) + flt(issued.amount)
	committed = sum(ordered[2].values())

	return {
		"restricted": False,
		"budget": budget,
		"actual": actual,
		"committed": committed,
		"percent": flt((actual + committed) / budget * 100, 1) if budget else None,
	}


def _projects(readable) -> dict:
	"""Billing and cost per project, as ERPNext keeps them on the project."""
	if "Project" not in readable:
		return {"restricted": True}
	rows = frappe.get_list(
		"Project",
		filters=_scoped("Project", {"status": ["!=", "Cancelled"]}),
		fields=[
			"name",
			"project_name",
			"status",
			"total_sales_amount",
			"total_billed_amount",
			"total_costing_amount",
			"total_expense_claim",
			"total_purchase_cost",
			"total_consumed_material_cost",
			"gross_margin",
			"per_gross_margin",
		],
		limit_page_length=0,
	)
	projects = sorted(
		(
			{
				"name": row.name,
				"title": row.project_name or row.name,
				"status": row.status,
				"ordered": flt(row.total_sales_amount),
				"billed": flt(row.total_billed_amount),
				"cost": flt(row.total_costing_amount)
				+ flt(row.total_expense_claim)
				+ flt(row.total_purchase_cost)
				+ flt(row.total_consumed_material_cost),
				"margin": flt(row.gross_margin),
				"margin_percent": flt(row.per_gross_margin, 1),
			}
			for row in rows
		),
		key=lambda row: (-row["billed"], -row["ordered"], row["title"]),
	)
	return {"restricted": False, "count": len(projects), "rows": projects[:PROJECT_LIST]}


def _health(readable, now) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy.

	`critical` is kept for customer money more than LONG_OVERDUE_DAYS late.
	"""
	checks = []

	def check(label, severity, doctype, filters, meta=None):
		checks.append(
			{
				"label": label,
				"severity": severity,
				"doctype": doctype,
				"count": _count(doctype, filters) if doctype in readable else None,
				"filters": _listed(filters),
				"meta": meta,
			}
		)

	long_overdue = {**OPEN, "due_date": ["<", str(add_days(now, -LONG_OVERDUE_DAYS))]}
	check(
		_("Customer invoices over {0} days overdue").format(LONG_OVERDUE_DAYS),
		"critical",
		"Sales Invoice",
		long_overdue,
	)

	overdue = {**OPEN, "due_date": ["between", [str(add_days(now, -LONG_OVERDUE_DAYS)), str(add_days(now, -1))]]}
	check(
		_("Customer invoices up to {0} days overdue").format(LONG_OVERDUE_DAYS),
		"warning",
		"Sales Invoice",
		overdue,
	)

	check(
		_("Supplier invoices past their due date"),
		"warning",
		"Purchase Invoice",
		{**OPEN, "due_date": ["<", str(now)]},
	)

	check(
		_("Goods received over {0} days ago, not yet billed").format(UNBILLED_RECEIPT_DAYS),
		"warning",
		"Purchase Receipt",
		{
			"docstatus": 1,
			"status": ["in", ["To Bill", "Partly Billed"]],
			"posting_date": ["<", str(add_days(now, -UNBILLED_RECEIPT_DAYS))],
		},
	)

	check(
		_("Bank transactions not yet reconciled"),
		"warning",
		"Bank Transaction",
		{"docstatus": 1, "unallocated_amount": [">", 0]},
	)

	check(
		_("Journal entries left in draft"),
		"warning",
		"Journal Entry",
		{"docstatus": 0},
	)

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
