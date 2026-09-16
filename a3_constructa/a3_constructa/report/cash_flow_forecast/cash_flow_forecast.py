# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Cash Flow Forecast - build sheet head 75, row 48.

Row 48 assumes ERPNext ships a Cash Flow Forecast report. It does not - it ships
"Cash Flow", which looks backwards. This looks forwards, which is what a
construction business needs: the risk is rarely whether a job is profitable, it
is whether there is cash in the week the subcontractors have to be paid.

Everything here is already committed, not estimated. Money in is invoices raised
and not yet settled, at their due dates. Money out is supplier invoices due,
purchase orders at their delivery dates, and certified work not yet invoiced.
Nothing speculative is included, so the forecast is a floor rather than a guess.

The `period` and `net_movement` fieldnames back the Cash Flow Forecast chart.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	start = getdate(filters.get("from_date") or nowdate())
	end = getdate(filters.get("to_date") or add_months(start, 3))
	interval = filters.get("interval") or "Weekly"

	buckets = build_buckets(start, end, interval)
	opening = flt(get_cash_balance(filters, start))

	inflow = get_receivable_due(filters, start, end)
	out_invoice = get_payable_due(filters, start, end)
	out_po = get_po_commitments(filters, start, end)
	out_cert = get_certified_unbilled(filters, start, end)

	data = []
	running = opening
	for label, b_start, b_end in buckets:
		receipts = sum_in_range(inflow, b_start, b_end)
		payments = (sum_in_range(out_invoice, b_start, b_end)
		            + sum_in_range(out_po, b_start, b_end)
		            + sum_in_range(out_cert, b_start, b_end))
		net = receipts - payments
		running += net
		data.append({
			"period": label,
			"opening_balance": running - net,
			"receipts": receipts,
			"supplier_invoices": sum_in_range(out_invoice, b_start, b_end),
			"purchase_orders": sum_in_range(out_po, b_start, b_end),
			"certified_work": sum_in_range(out_cert, b_start, b_end),
			"payments": payments,
			"net_movement": net,
			"closing_balance": running,
		})

	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 130},
		{"fieldname": "opening_balance", "label": _("Opening"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "receipts", "label": _("Receipts Due"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "supplier_invoices", "label": _("Supplier Invoices"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "purchase_orders", "label": _("PO Deliveries"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "certified_work", "label": _("Certified Work"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "payments", "label": _("Payments Due"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "net_movement", "label": _("Net Movement"), "fieldtype": "Currency",
		 "width": 140},
		{"fieldname": "closing_balance", "label": _("Closing"), "fieldtype": "Currency",
		 "width": 140},
	]


def build_buckets(start, end, interval):
	"""Label and date range per period, forward from today."""
	step = {"Weekly": 7, "Daily": 1, "Monthly": 30}.get(interval, 7)
	buckets = []
	cursor = start
	while cursor <= end:
		bucket_end = min(add_days(cursor, step - 1), end)
		buckets.append((cursor.strftime("%d %b %Y"), cursor, bucket_end))
		cursor = add_days(bucket_end, 1)
	return buckets


def sum_in_range(rows, start, end):
	return sum(flt(r["amount"]) for r in rows
	           if r["date"] and start <= getdate(r["date"]) <= end)


def get_cash_balance(filters, as_on):
	"""What is in the bank and the cash box today."""
	conditions = ["gle.is_cancelled = 0", "gle.posting_date < %(as_on)s",
	              "acc.account_type in ('Cash', 'Bank')"]
	values = {"as_on": as_on}
	if filters.get("company"):
		conditions.append("gle.company = %(company)s")
		values["company"] = filters.company

	rows = frappe.db.sql(
		"""
		select sum(gle.debit) - sum(gle.credit)
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {conditions}
		""".format(conditions=" and ".join(conditions)),
		values,
	)
	return rows[0][0] if rows else 0


def _party_conditions(filters, alias):
	conditions = ["%s.docstatus = 1" % alias, "%s.outstanding_amount > 0" % alias]
	values = {}
	if filters.get("company"):
		conditions.append("%s.company = %%(company)s" % alias)
		values["company"] = filters.company
	if filters.get("project"):
		conditions.append("%s.project = %%(project)s" % alias)
		values["project"] = filters.project
	return conditions, values


def get_receivable_due(filters, start, end):
	conditions, values = _party_conditions(filters, "si")
	rows = frappe.db.sql(
		"""
		select si.due_date as `date`, sum(si.outstanding_amount) as amount
		from `tabSales Invoice` si
		where {conditions}
		group by si.due_date
		""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	# Anything already overdue is treated as due in the first period rather than
	# dropped: it is still cash the business is waiting on.
	return [{"date": r.date if r.date and getdate(r.date) >= start else start,
	         "amount": r.amount} for r in rows]


def get_payable_due(filters, start, end):
	conditions, values = _party_conditions(filters, "pi")
	rows = frappe.db.sql(
		"""
		select pi.due_date as `date`, sum(pi.outstanding_amount) as amount
		from `tabPurchase Invoice` pi
		where {conditions}
		group by pi.due_date
		""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	return [{"date": r.date if r.date and getdate(r.date) >= start else start,
	         "amount": r.amount} for r in rows]


def get_po_commitments(filters, start, end):
	"""Ordered but not yet invoiced, falling due at the delivery date."""
	conditions = ["po.docstatus = 1", "po.status not in ('Closed', 'Completed')",
	              "poi.schedule_date between %(start)s and %(end)s"]
	values = {"start": start, "end": end}
	if filters.get("company"):
		conditions.append("po.company = %(company)s")
		values["company"] = filters.company
	if filters.get("project"):
		conditions.append("po.project = %(project)s")
		values["project"] = filters.project

	rows = frappe.db.sql(
		"""
		select poi.schedule_date as `date`,
		       sum(poi.base_amount - (poi.billed_amt * ifnull(po.conversion_rate, 1))) as amount
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent
		where {conditions}
		group by poi.schedule_date
		""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	return [{"date": r.date, "amount": max(flt(r.amount), 0)} for r in rows]


def get_certified_unbilled(filters, start, end):
	"""Subcontractor work certified and not yet invoiced - net of retention."""
	conditions = ["wc.docstatus = 1"]
	values = {}
	if filters.get("project"):
		conditions.append("wc.project = %(project)s")
		values["project"] = filters.project

	rows = frappe.db.sql(
		"""
		select wc.period_to as `date`, sum(wc.total_net_payable) as amount
		from `tabWork Certificate` wc
		where {conditions}
		group by wc.period_to
		""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	return [{"date": r.date if r.date and getdate(r.date) >= start else start,
	         "amount": r.amount} for r in rows]
