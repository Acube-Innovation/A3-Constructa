# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Cash and Bank Balance - build sheet head 76, row 56.

What is in the bank and the cash boxes right now, one line per account.

This exists as a report rather than a plain Number Card because the card had to
filter GL Entry on `account_type`, and GL Entry has no such column - the account
type lives on Account. A Document Type card cannot join, so the join happens
here and the card reads the `balance` column.

Keep the `balance` fieldname: the "Cash & Bank Balance" number card binds to it.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

CASH_AND_BANK = ("Cash", "Bank")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "account", "label": _("Account"), "fieldtype": "Link",
		 "options": "Account", "width": 260},
		{"fieldname": "account_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "company", "label": _("Company"), "fieldtype": "Link",
		 "options": "Company", "width": 180},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	conditions = ["gle.is_cancelled = 0", "acc.account_type in %(types)s", "acc.is_group = 0"]
	values = {"types": CASH_AND_BANK}

	if filters.get("company"):
		conditions.append("gle.company = %(company)s")
		values["company"] = filters.company

	# A balance is always "as at" a date; default to today rather than summing
	# entries dated into the future.
	conditions.append("gle.posting_date <= %(as_on)s")
	values["as_on"] = getdate(filters.get("as_on") or nowdate())

	rows = frappe.db.sql(
		"""
		select gle.account, gle.company, acc.account_type,
		       sum(gle.debit) - sum(gle.credit) as balance
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {conditions}
		group by gle.account, gle.company, acc.account_type
		order by balance desc
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	for r in rows:
		r["balance"] = flt(r.balance)
	return rows
