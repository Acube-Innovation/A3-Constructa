# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Material Issue Register - build sheet head 48, row 20.

Every line issued out of store, with what it was issued against. This is the
document a quantity surveyor reconciles against the BOQ, so it reads off Stock
Entry Detail rather than the ledger: the cost code and WBS live on the line.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Issues out of store. A transfer between warehouses is a movement, not
# consumption, so it does not belong in an issue register.
ISSUE_PURPOSES = ("Material Issue",)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "parent", "label": _("MIN No"), "fieldtype": "Link",
		 "options": "Stock Entry", "width": 150},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link",
		 "options": "Item", "width": 160},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM",
		 "width": 80},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "amount", "label": _("Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link",
		 "options": "Project", "width": 130},
		{"fieldname": "cost_head", "label": _("Cost Head"), "fieldtype": "Link",
		 "options": "Cost Head", "width": 130},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS",
		 "width": 130},
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 130},
		{"fieldname": "s_warehouse", "label": _("Issued From"), "fieldtype": "Link",
		 "options": "Warehouse", "width": 150},
		{"fieldname": "issued_to", "label": _("Issued To"), "fieldtype": "Data", "width": 150},
	]


def get_data(filters):
	conditions = ["se.docstatus = 1", "se.purpose in %(purposes)s"]
	values = {"purposes": ISSUE_PURPOSES}

	for key, column in (("project", "sed.project"), ("cost_head", "sed.cost_head"),
	                    ("wbs", "sed.wbs"), ("cost_code", "sed.cost_code"),
	                    ("item_code", "sed.item_code"), ("company", "se.company")):
		if filters.get(key):
			conditions.append("%s = %%(%s)s" % (column, key))
			values[key] = filters[key]

	if filters.get("from_date"):
		conditions.append("se.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("se.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	rows = frappe.db.sql(
		"""
		select se.posting_date, sed.parent, sed.item_code, sed.qty, sed.uom,
		       sed.basic_rate as rate, sed.amount, sed.project, sed.cost_head,
		       sed.wbs, sed.cost_code, sed.s_warehouse, sed.t_warehouse,
		       se.stock_entry_type
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent
		where {conditions}
		order by se.posting_date desc, sed.parent, sed.idx
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	for r in rows:
		r["amount"] = flt(r.amount)
		# An issue has no destination warehouse, so "issued to" is the project
		# cost centre the cost code points at, falling back to the WBS.
		r["issued_to"] = r.t_warehouse or r.wbs or r.cost_code or ""

	return rows
