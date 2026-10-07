# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-13C: earned value needs the frame's cost to be on the books.

The concrete frame (WBS Substructure and frame) is about two-thirds built by its
progress log, but until now only a few hundred dollars of material issued had
reached it: the ready-mix concrete and formwork came on account from Congo Steel
& Cement. Their three monthly invoices are booked here, on the frame's WBS and
the structure cost code, in July, August and September, so actual cost grows
month by month alongside the work, and the frame shows a little over budget
(CPI just under 1) while the architectural works and the ground-floor tiling
show worse.
"""

import frappe
from frappe.utils import add_days, flt, getdate

from a3_constructa.demo.masiha.common import COMPANY, as_user, comment, exists, log, project

SUPPLIER = "Congo Steel & Cement SARL"
INVOICES = [  # bill no, date, amount, what
	("CSC-RMX-0712", "2026-07-31", 34000, "Ready-mix C30/37 and formwork hire, July: foundations and ground beams"),
	("CSC-RMX-0841", "2026-08-31", 30000, "Ready-mix C30/37 and formwork hire, August: ground-floor columns and slab"),
	("CSC-RMX-0957", "2026-09-30", 27000, "Ready-mix C30/37 and formwork hire, September: first-floor columns"),
]
TAGS = {"cost_head": "MSS-ES", "wbs": "MSS-W-ES", "cost_code": "MSS-CC-STR-M"}


def run():
	p = project()
	made = []
	for bill_no, date, amount, what in INVOICES:
		if exists("Purchase Invoice", {"bill_no": bill_no, "company": COMPANY, "docstatus": 1}):
			continue
		pi = frappe.get_doc({
			"doctype": "Purchase Invoice", "company": COMPANY, "supplier": SUPPLIER, "posting_date": date, "set_posting_time": 1,
			"bill_no": bill_no, "bill_date": date, "due_date": add_days(getdate(date), 30), "project": p, "update_stock": 0,
			"items": [{"item_name": "Ready-mix concrete and formwork (on account)", "description": what, "qty": 1, "uom": "Nos",
			           "rate": amount, "expense_account": "Project Materials - MSS", "project": p, **TAGS}],
		})
		pi.flags.silent_three_way = True
		with as_user("finance"):
			pi.insert(ignore_permissions=True)
			pi.submit()
		made.append(pi.name)
	if made:
		comment("Purchase Invoice", made[-1], "Frame valuation agreed with Congo Steel & Cement: concrete and formwork to the first-floor columns.", "pm", None)
	total = sum(flt(i[2]) for i in INVOICES)
	log(f"frame cost on the books: {len(made)} invoices booked now, ${total:,.0f} in all (Jul-Sep) on MSS-W-ES / MSS-CC-STR-M")
