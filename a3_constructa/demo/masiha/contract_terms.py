# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-04A: contract terms on the awards and the hospital's sales order.

- A3 Constructa Settings: contracts are paid Net 30 Days and carry DRC VAT 16%.
- The Administrative Centre is a lump sum: 5% retention capped at 5%, a 10%
  advance recovered at 20% of each certificate.
- The hospital is re-measured: 10% retention capped at 5% of the contract, a
  15% advance recovered at 20% of each certificate.
- The hospital gets its WBS (one node per trade under the project's top node),
  its draft order's lines name their tender BOQ line, the order fills in the
  terms and each line's WBS, and sales submits it.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, log

TERMS = {
	"Administrative Centre": {"contract_type": "Lump Sum", "retention_cap_percent": 5, "advance_recovery_percent": 20},
	"Hospital extension": {"contract_type": "Re-measured", "retention_percent": 10, "retention_cap_percent": 5,
	                       "advance_percent": 15, "advance_recovery_percent": 20},
	"Provincial Assembly": {"contract_type": "Lump Sum", "retention_cap_percent": 5},
}
HOSPITAL_WBS = [
	("HGR-W-PRE", "Preliminaries and site establishment", "MSS-PRE"),
	("HGR-W-ES", "Substructure and frame", "MSS-ES"),
	("HGR-W-DW", "Doors and windows", "MSS-AR-DW"),
	("HGR-W-FL", "Flooring", "MSS-AR-FL"),
	("HGR-W-PT", "Painting", "MSS-AR-PT"),
	("HGR-W-MEP", "MEP, medical gases and standby power", "MSS-MEP"),
]


def run():
	settings = frappe.get_single("A3 Constructa Settings")
	if not settings.contract_payment_terms:
		settings.contract_payment_terms = "Net 30 Days"
		settings.contract_taxes = frappe.db.get_value("Sales Taxes and Charges Template", {"company": COMPANY}, "name")
		settings.save(ignore_permissions=True)
	for title, terms in TERMS.items():
		award = frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "title": ["like", f"%{title}%"]}, "name")
		if award and not frappe.db.get_value("Awarded Quotation", award, "retention_cap_percent"):
			frappe.db.set_value("Awarded Quotation", award, terms)

	hospital = frappe.db.get_value("Awarded Quotation", {"title": ["like", "Hospital extension%"]}, ["name", "project"], as_dict=True)
	if not hospital or not hospital.project:
		log("hospital not handed over; run the handover stage first")
		return
	so = frappe.db.get_value("Sales Order", {"awarded_quotation": hospital.name, "docstatus": ["<", 2]}, ["name", "docstatus"], as_dict=True)
	if not so or so.docstatus == 1:
		log("hospital order already submitted" if so else "no hospital order")
		return
	made = hospital_wbs(hospital.project)
	order = map_and_submit(so.name, hospital.name)
	log(f"Contract terms set; hospital WBS: {made}; {order}")


def hospital_wbs(project):
	if frappe.db.exists("WBS", "HGR-W"):
		return "already there"
	with as_user("pm"):
		root = frappe.get_doc({"doctype": "WBS", "wbs_code": "HGR-W", "wbs_name": "Hospital extension: maternity and theatre block",
		                       "project": project, "is_group": 1, "status": "Active", "responsible_person": employee("Didier")})
		root.flags.ignore_permissions = True
		root.insert()
		for code, name, head in HOSPITAL_WBS:
			node = frappe.get_doc({"doctype": "WBS", "wbs_code": code, "wbs_name": name, "project": project, "parent_wbs": "HGR-W",
			                       "cost_head": head, "status": "Active", "responsible_person": employee("Didier")})
			node.flags.ignore_permissions = True
			node.insert()
	return f"HGR-W with {len(HOSPITAL_WBS)} trade nodes"


def employee(first_name):
	return frappe.db.get_value("Employee", {"first_name": first_name, "company": COMPANY}, "name")


def map_and_submit(name, award):
	"""Name each line's tender BOQ line (the handover made them in the quotation's order)."""
	quotation = frappe.db.get_value("Awarded Quotation", award, "quotation")
	q = frappe.get_doc("Quotation", quotation)
	with as_user("sales"):
		so = frappe.get_doc("Sales Order", name)
		for row, line in zip(so.items, q.items):
			row.boq, row.boq_ref = q.boq, line.boq_ref
		so.flags.ignore_permissions = True
		so.save()
		so.submit()
	frappe.db.set_value("Sales Order", name, "modified", at(0, 16), update_modified=False)
	comment("Sales Order", name, "Contract signed with the hospital board; order submitted on the award's terms.", "sales", at(0, 16, 5))
	so.reload()
	return f"{name} submitted: {len(so.items)} lines on BOQ lines and WBS, ${so.net_total:,.2f} + VAT = ${so.grand_total:,.2f}"
