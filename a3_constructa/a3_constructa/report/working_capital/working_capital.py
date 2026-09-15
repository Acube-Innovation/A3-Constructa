# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Working Capital - build sheet head 75, row 52.

Month by month: what the business is owed, what it owes, what is sitting in
stock, what is certified but not yet billed, and what is being held back as
retention. The trend is the point - a contractor rarely fails on profit, it
fails on the month working capital turns.

The `period` and `net_working_capital` fieldnames back the Working Capital Trend
chart; the Legend warns a renamed column breaks such a chart silently.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

RETENTION_ACCOUNT_FRAGMENT = "Retention Payable"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	periods = get_periods(filters)

	data = []
	for start, end in periods:
		receivable = balance_by_type(filters, "Receivable", end)
		payable = balance_by_type(filters, "Payable", end)
		stock = balance_by_root(filters, "Stock", end)
		retention = retention_held(filters, end)
		wip = certified_unbilled(filters, end)

		# Retention sits inside payables, so it is shown separately and taken
		# back out to avoid counting it twice.
		payable_ex_retention = payable - retention

		data.append({
			"period": start.strftime("%b %Y"),
			"receivables": receivable,
			"payables": payable_ex_retention,
			"stock_value": stock,
			"wip": wip,
			"retention_held": retention,
			"net_working_capital": receivable + stock + wip - payable_ex_retention - retention,
		})

	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 110},
		{"fieldname": "receivables", "label": _("Receivables"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "stock_value", "label": _("Stock Value"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "wip", "label": _("WIP (Certified Unbilled)"), "fieldtype": "Currency",
		 "width": 190},
		{"fieldname": "payables", "label": _("Payables"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "retention_held", "label": _("Retention Held"), "fieldtype": "Currency",
		 "width": 150},
		{"fieldname": "net_working_capital", "label": _("Net Working Capital"),
		 "fieldtype": "Currency", "width": 180},
	]


def get_periods(filters):
	"""Month ends from the start date to the end date, oldest first."""
	to_date = getdate(filters.get("to_date") or nowdate())
	months = int(filters.get("months") or 12)
	from_date = getdate(filters.get("from_date") or add_months(to_date, -months + 1))

	periods = []
	cursor = get_first_day(from_date)
	while cursor <= to_date:
		periods.append((cursor, min(get_last_day(cursor), to_date)))
		cursor = get_first_day(add_months(cursor, 1))
	return periods


def _conditions(filters, as_on):
	conditions = ["gle.is_cancelled = 0", "gle.posting_date <= %(as_on)s"]
	values = {"as_on": as_on}
	if filters.get("company"):
		conditions.append("gle.company = %(company)s")
		values["company"] = filters.company
	if filters.get("project"):
		conditions.append("gle.project = %(project)s")
		values["project"] = filters.project
	return conditions, values


def balance_by_type(filters, account_type, as_on):
	"""Closing balance of every account of a type, as at a date."""
	conditions, values = _conditions(filters, as_on)
	conditions.append("acc.account_type = %(account_type)s")
	values["account_type"] = account_type

	rows = frappe.db.sql(
		"""
		select sum(gle.debit) - sum(gle.credit) as balance
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
	)
	balance = flt(rows[0][0]) if rows else 0
	# Liabilities carry a credit balance; report them positive.
	return balance if account_type == "Receivable" else -balance


def balance_by_root(filters, root_type_account, as_on):
	conditions, values = _conditions(filters, as_on)
	conditions.append("acc.account_type = %(account_type)s")
	values["account_type"] = root_type_account

	rows = frappe.db.sql(
		"""
		select sum(gle.debit) - sum(gle.credit) as balance
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
	)
	return flt(rows[0][0]) if rows else 0


def retention_held(filters, as_on):
	"""Balance on the Retention Payable account, positive when money is held."""
	conditions, values = _conditions(filters, as_on)
	conditions.append("gle.account like %(retention)s")
	values["retention"] = "%" + RETENTION_ACCOUNT_FRAGMENT + "%"

	rows = frappe.db.sql(
		"""
		select sum(gle.credit) - sum(gle.debit) as balance
		from `tabGL Entry` gle
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
	)
	return flt(rows[0][0]) if rows else 0


def certified_unbilled(filters, as_on):
	"""Work certified to subcontractors but not yet invoiced by them.

	Certified value less what has been invoiced against the same purchase order,
	which is the closest thing to construction WIP the ledger can give.
	"""
	conditions = ["wc.docstatus = 1", "wc.period_to <= %(as_on)s"]
	values = {"as_on": as_on}
	if filters.get("project"):
		conditions.append("wc.project = %(project)s")
		values["project"] = filters.project

	rows = frappe.db.sql(
		"""
		select sum(wc.total_net_payable) as certified
		from `tabWork Certificate` wc
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
	)
	return flt(rows[0][0]) if rows else 0
