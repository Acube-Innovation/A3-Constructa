# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-03C: the hospital extension is won and handed over in one step.

The client's letter of award arrives for quotation SAL-QTN-2026-00006-1 (the
$528,625 revision the managing director approved). The award is created from
the quotation, its programme dates are set, and "Hand over to project" makes
the project, a draft sales order with one line per BOQ line, the budget BOQ
revision 0 at the estimate's cost rates, and copies the tender's notes and
attachments onto the project.

Cost heads name the contract works item their lines are billed under; a general
item covers preliminaries and the contingency.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, insert, log

HOSPITAL = "Hospital extension: maternity and theatre block"
GENERAL_ITEM = "CW-GEN"
HEAD_ITEMS = {"MSS-ES": "CW-STRUCT", "MSS-AR": "CW-ARCH", "MSS-MEP": "CW-MEP", "MSS-PRE": GENERAL_ITEM}


def run():
	set_contract_items()
	opp = frappe.db.get_value("Opportunity", {"title": HOSPITAL}, "name")
	quotation = frappe.db.get_value("Quotation", {"opportunity": opp, "docstatus": 1, "boq": ["is", "set"]}, "name") if opp else None
	if not quotation:
		log("no submitted hospital quotation; run the quotations stage first")
		return
	if frappe.db.exists("Awarded Quotation", {"quotation": quotation}):
		log("hospital already awarded")
		return
	from a3_constructa.api.award_handover import hand_over, make_awarded_quotation

	with as_user("md"):
		award = make_awarded_quotation(quotation)["name"]
		a = frappe.get_doc("Awarded Quotation", award)
		a.update({"award_reference": "HGR/LOA/2026/014", "start_date": day(27), "end_date": day(27 + 540),
		          "retention_percent": 5, "advance_percent": 15, "defects_liability_months": 12})
		a.save()
	frappe.db.set_value("Awarded Quotation", award, {"creation": at(0, 11), "modified": at(0, 11)}, update_modified=False)
	comment("Awarded Quotation", award, "Letter of award received from the hospital board: $528,625, 18 months from 2 November.", "md", at(0, 11, 5))
	with as_user("md"):
		done = hand_over(award, project_name="Hospital extension: maternity and theatre block", sales_order_lines="Per BOQ line")
	log(f"{award} from {quotation}; handed over: " + "; ".join(done["created"]))


def set_contract_items():
	if not frappe.db.exists("Item", GENERAL_ITEM):
		insert({"doctype": "Item", "item_code": GENERAL_ITEM, "item_name": "Contract works - general", "item_group": "Contract Works",
		        "stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1, "is_purchase_item": 0,
		        "description": "Preliminaries, contingency and other contract work billed outside a trade package."})
	for head, item in HEAD_ITEMS.items():
		if frappe.db.exists("Cost Head", head) and not frappe.db.get_value("Cost Head", head, "sales_item"):
			frappe.db.set_value("Cost Head", head, "sales_item", item)
	if not frappe.db.get_single_value("A3 Constructa Settings", "default_contract_item"):
		frappe.db.set_single_value("A3 Constructa Settings", "default_contract_item", GENERAL_ITEM)
