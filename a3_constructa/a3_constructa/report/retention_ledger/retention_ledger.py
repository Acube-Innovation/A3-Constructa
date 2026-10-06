# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Retention Ledger - catalogue 4.5 and 12.4: retention held, released and still
outstanding, both directions.

- Receivable: what clients hold back from us on IPCs, per award, less the
  retention release invoices.
- Payable: what we hold back from subcontractors on Work Certificates, per
  project and subcontractor (released when their defects liability ends).
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = []
	if filters.get("direction") in (None, "", "Receivable"):
		data += receivable(filters)
	if filters.get("direction") in (None, "", "Payable"):
		data += payable(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	return [
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 105},
		{"fieldname": "reference", "label": _("Award / Project"), "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 135},
		{"fieldname": "party", "label": _("Client / Subcontractor"), "fieldtype": "Data", "width": 220},
		{"fieldname": "held", "label": _("Held"), **cur, "width": 120},
		{"fieldname": "released", "label": _("Released"), **cur, "width": 120},
		{"fieldname": "balance", "label": _("Balance"), **cur, "width": 120},
		{"fieldname": "documents", "label": _("Documents"), "fieldtype": "Int", "width": 95},
		{"fieldname": "note", "label": _("Next release"), "fieldtype": "Data", "width": 260},
		{"fieldname": "reference_doctype", "label": _("Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def receivable(filters):
	from frappe.utils import add_months, formatdate

	conditions = {"docstatus": ["<", 2], "status": ["!=", "Cancelled"]}
	if filters.get("company"):
		conditions["company"] = filters.company
	rows = []
	for a in frappe.get_list("Awarded Quotation", filters=conditions,
	                         fields=["name", "customer", "currency", "practical_completion_date", "defects_liability_months",
	                                 "retention_release_1", "retention_release_2"], limit_page_length=0):
		held = frappe.db.sql("""select sum(retention_this_period), count(name) from `tabClient IPC`
			where awarded_quotation = %s and docstatus = 1 and retention_this_period > 0""", a.name)[0]
		if not flt(held[0]):
			continue
		released = sum(flt(frappe.db.get_value("Sales Invoice", n, "net_total")) for n in (a.retention_release_1, a.retention_release_2)
		               if n and frappe.db.get_value("Sales Invoice", n, "docstatus") == 1)
		if not a.practical_completion_date:
			note = _("Half at practical completion")
		elif not a.retention_release_1:
			note = _("Half due now (practical completion {0})").format(formatdate(a.practical_completion_date))
		elif not a.retention_release_2:
			note = _("Half at the end of the DLP, {0}").format(formatdate(add_months(a.practical_completion_date, int(a.defects_liability_months or 0))))
		else:
			note = _("Fully released")
		rows.append({"direction": _("Receivable"), "reference_doctype": "Awarded Quotation", "reference": a.name, "party": a.customer,
		             "held": flt(held[0]), "released": released, "balance": flt(held[0]) - released, "documents": held[1],
		             "note": note, "currency": a.currency})
	return rows


def payable(filters):
	values = {}
	condition = ""
	if filters.get("company"):
		condition = "and p.company = %(company)s"
		values["company"] = filters.company
	rows = []
	for r in frappe.db.sql(f"""select wc.project, wc.supplier, sum(wc.total_retention) held, count(wc.name) n
		from `tabWork Certificate` wc left join `tabProject` p on p.name = wc.project
		where wc.docstatus = 1 and wc.total_retention > 0 {condition}
		group by wc.project, wc.supplier""", values, as_dict=True):
		rows.append({"direction": _("Payable"), "reference_doctype": "Project", "reference": r.project, "party": r.supplier,
		             "held": flt(r.held), "released": 0, "balance": flt(r.held), "documents": r.n,
		             "note": _("At the end of the subcontract's defects liability"), "currency": frappe.defaults.get_global_default("currency")})
	return rows


def get_summary(data):
	rec = sum(r["balance"] for r in data if r["reference_doctype"] == "Awarded Quotation")
	pay = sum(r["balance"] for r in data if r["reference_doctype"] == "Project")
	return [
		{"label": _("Clients hold (receivable)"), "value": rec, "datatype": "Currency", "indicator": "Green"},
		{"label": _("We hold (payable)"), "value": pay, "datatype": "Currency", "indicator": "Orange"},
	]
