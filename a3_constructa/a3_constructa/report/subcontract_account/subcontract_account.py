# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Subcontract Account - catalogue 9.6: per subcontract PO, the contract value, what
the Work Certificates have certified, the retention held and the deductions taken
off it, what has been invoiced and paid, and the balance still to pay.

A subcontract PO is one a Work Certificate certifies against (or one ERPNext marks
as subcontracted). Paid is the cash paid on the certificates' purchase invoices:
the journal that moves retention to Retention Payable settles part of each
invoice too, but it is not a payment. Balance = net certified - paid, so
certificates not yet invoiced count as owed.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{"fieldname": "subcontract_po", "label": _("Subcontract PO"), "fieldtype": "Link", "options": "Purchase Order", "width": 150},
		{"fieldname": "supplier", "label": _("Subcontractor"), "fieldtype": "Link", "options": "Supplier", "width": 190},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "contract_value", "label": _("Contract Value"), **cur, "width": 120},
		{"fieldname": "certified", "label": _("Certified"), **cur, "width": 110},
		{"fieldname": "certified_percent", "label": _("Certified %"), "fieldtype": "Percent", "width": 95},
		{"fieldname": "retention", "label": _("Retention Held"), **cur, "width": 115},
		{"fieldname": "deductions", "label": _("Deductions"), **cur, "width": 105},
		{"fieldname": "net_certified", "label": _("Net Certified"), **cur, "width": 115},
		{"fieldname": "invoiced", "label": _("Invoiced"), **cur, "width": 105},
		{"fieldname": "paid", "label": _("Paid"), **cur, "width": 105},
		{"fieldname": "balance", "label": _("Balance to Pay"), **cur, "width": 120},
		{"fieldname": "certificates", "label": _("Certificates"), "fieldtype": "Int", "width": 95},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	conditions = {"docstatus": 1}
	for f in ("company", "supplier", "project"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	certified_pos = set(frappe.get_all("Work Certificate", filters={"docstatus": 1, "subcontract_po": ["is", "set"]}, pluck="subcontract_po"))
	pos = frappe.get_list("Purchase Order", filters=conditions, or_filters={"name": ["in", list(certified_pos) or [""]], "is_subcontracted": 1},
	                      fields=["name", "supplier", "project", "net_total", "currency"], order_by="name asc", limit_page_length=0)
	data = []
	for po in pos:
		wcs = frappe.get_all("Work Certificate", filters={"subcontract_po": po.name, "docstatus": 1},
		                     fields=["name", "total_amount", "total_retention", "total_deductions", "total_net_payable", "purchase_invoice", "project"])
		certified = sum(flt(w.total_amount) for w in wcs)
		retention = sum(flt(w.total_retention) for w in wcs)
		deductions = sum(flt(w.total_deductions) for w in wcs)
		net = sum(flt(w.total_net_payable) for w in wcs)
		invoiced = paid = 0.0
		for w in wcs:
			pi = frappe.db.get_value("Purchase Invoice", w.purchase_invoice, ["docstatus", "grand_total", "outstanding_amount", "retention_journal"],
			                         as_dict=True) if w.purchase_invoice else None
			if not pi or pi.docstatus != 1:
				continue
			moved = flt(w.total_retention) if pi.retention_journal and frappe.db.get_value("Journal Entry", pi.retention_journal, "docstatus") == 1 else 0
			invoiced += flt(pi.grand_total)
			paid += flt(pi.grand_total) - flt(pi.outstanding_amount) - moved
		data.append({"subcontract_po": po.name, "supplier": po.supplier, "project": po.project or (wcs[0].project if wcs else None),
		             "contract_value": flt(po.net_total), "certified": certified,
		             "certified_percent": certified / flt(po.net_total) * 100 if flt(po.net_total) else None,
		             "retention": retention, "deductions": deductions, "net_certified": net, "invoiced": invoiced, "paid": flt(paid, 2),
		             "balance": flt(net - paid, 2), "certificates": len(wcs), "currency": po.currency})
	return data


def get_summary(data):
	if not data:
		return []
	currency = data[0]["currency"]
	total = lambda f: sum(flt(r[f]) for r in data)
	return [
		{"label": _("Certified"), "value": total("certified"), "datatype": "Currency", "currency": currency, "indicator": "Blue"},
		{"label": _("Retention held"), "value": total("retention"), "datatype": "Currency", "currency": currency},
		{"label": _("Deductions"), "value": total("deductions"), "datatype": "Currency", "currency": currency},
		{"label": _("Balance to pay"), "value": total("balance"), "datatype": "Currency", "currency": currency,
		 "indicator": "Red" if total("balance") > 0.005 else "Green"},
	]
