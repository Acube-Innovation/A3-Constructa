# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-04B: the hospital is billed by milestones; the Administrative Centre by progress claims.

- The Administrative Centre's billing basis becomes "Progress claims": it is
  already billed by progress claim ACC-SINV-2026-00006, so its milestones only
  plan (no milestone falls due, nothing is billed twice).
- Each hospital milestone names the component it bills. The advance payment
  guarantee and insurances are lodged today, so that milestone (15%) is complete
  and due; finance bills it and submits the invoice. The hospital order's payment
  schedule follows the programme.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, day, log

HOSPITAL_COMPONENTS = {
	"Advance payment guarantee and insurances lodged": "Preliminaries",
	"Mobilisation and site set-up": "Preliminaries",
	"Substructure": "Earthworks / Structural",
	"Frame and envelope": "Earthworks / Structural",
	"Finishes and theatre fit-out": "Flooring",
	"MEP, commissioning and handover": "MEP / Others / Misc.",
}
ADVANCE = "Advance payment guarantee and insurances lodged"


def run():
	main = frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "title": ["like", "%Administrative Centre%"]}, "name")
	if main and frappe.db.get_value("Awarded Quotation", main, "billing_basis") != "Progress claims":
		frappe.db.set_value("Awarded Quotation", main, "billing_basis", "Progress claims")
	hospital = frappe.db.get_value("Awarded Quotation", {"title": ["like", "Hospital extension%"]}, "name")
	if not hospital:
		log("no hospital award; run the handover stage first")
		return
	if frappe.db.exists("Awarded Quotation Milestone", {"parent": hospital, "sales_invoice": ["is", "set"]}):
		log("hospital milestones already billed")
		return
	from a3_constructa.api.milestone_billing import bill_due_milestones

	with as_user("pm"):
		a = frappe.get_doc("Awarded Quotation", hospital)
		a.billing_basis = "Milestones"
		for row in a.milestones:
			row.component = HOSPITAL_COMPONENTS.get(row.milestone)
			if row.milestone == ADVANCE:
				row.actual_end = day(0)
		a.flags.ignore_permissions = True
		a.save()
	comment("Awarded Quotation", hospital, "Advance payment guarantee (15%) and the contractor's all-risks policy delivered to the hospital board.", "pm", at(0, 9))
	with as_user("finance"):
		invoices = bill_due_milestones(hospital)
		for name in invoices:
			si = frappe.get_doc("Sales Invoice", name)
			si.flags.ignore_permissions = True
			si.submit()
	so = frappe.db.get_value("Sales Order", {"awarded_quotation": hospital, "docstatus": 1}, "name")
	rows = frappe.db.count("Payment Schedule", {"parent": so}) if so else 0
	log(f"{main}: progress claims; {hospital}: billed {', '.join(invoices)}; {so} payment schedule: {rows} milestone rows")
