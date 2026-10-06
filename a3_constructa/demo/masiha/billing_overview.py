# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-04: a case for each check on the Sales & Billing overview.

Failing cases (each check also has a passing one from earlier stages):
- Invoices past their due date: the August progress claim, $179,100 still unpaid.
- Certified IPCs not invoiced, and IPCs not certified after 21 days: the committee
  wing at the Provincial Assembly, billed by IPCs, has a slow engineer: IPC 1 was
  only certified 12 days ago and is not yet invoiced; IPC 2 has been with him 26 days.
- Guarantees expiring in 30 days: the committee wing's performance bond runs out in 18 days.
- Milestones due and not billed: the emergency roof's temporary waterproofing was
  finished yesterday; its 40% is due.
- Retention due for release: the school's second half (from P-04D).
Passing cases: the Administrative Centre's IPC 3 went to the client today, the
advance guarantee runs to next June, the hospital's milestones are all ahead.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, as_user, at, comment, day, log

WING = "Provincial Assembly: committee wing refurbishment"
EMERGENCY = "Provincial Assembly: emergency roof leak repairs"
ROOT = "PAC-W"
COMPONENTS = [
	("Strip-out and making good", 1, "Lump Sum", 9_400),
	("Partitions and ceilings", 640, "Square Meter", 38),
	("Floor finishes", 410, "Square Meter", 34),
	("Electrical and data", 1, "Lump Sum", 21_600),
]


def run():
	if frappe.db.exists("Awarded Quotation", {"title": WING}):
		log("billing overview cases already present")
		return
	award, project = committee_wing()
	from a3_constructa.a3_constructa.doctype.client_ipc.client_ipc import get_contract_lines

	with as_user("qs"):
		lines = get_contract_lines(award)
	ipc1 = certificate(award, lines, -95, -60, {"Strip": 1, "Partitions": 240, "Electrical": 0.2}, sent=-55, certified=-12)
	ipc2 = certificate(award, lines, -59, -30, {"Partitions": 260, "Floor": 120, "Electrical": 0.3}, sent=-26, certified=None)
	comment("Client IPC", ipc2, "Chased the Assembly's engineer again: he is still on IPC 1's re-measure and has not opened this one.", "qs", at(-5, 11))
	bond = performance_bond(award, project)
	roof = emergency_milestones()
	log(f"{award} ({project}): {ipc1} certified, not invoiced; {ipc2} with the client 26 days; bond {bond} expires in 18 days; {roof}")


def committee_wing():
	with as_user("md"):
		a = frappe.get_doc({"doctype": "Awarded Quotation", "title": WING, "customer": CUSTOMER, "company": COMPANY, "currency": "USD",
		                    "award_date": day(-110), "award_reference": "GPE/AP/2026/014", "status": "Awarded", "start_date": day(-100),
		                    "end_date": day(60), "retention_percent": 5, "retention_cap_percent": 5, "advance_percent": 0,
		                    "defects_liability_months": 12, "contract_type": "Re-measured", "billing_basis": "Progress claims",
		                    "scope": "Refurbishment of the committee wing: new partitions, ceilings, floors, electrical and data.",
		                    "components": [{"component": c, "qty": q, "uom": u, "rate": r} for c, q, u, r in COMPONENTS]})
		a.flags.ignore_permissions = True
		a.insert()
	# Handed over the usual way: a project and the draft contract order.
	from a3_constructa.api.award_handover import hand_over

	with as_user("md"):
		hand_over(a.name, project_name="Provincial Assembly committee wing", make_budget_boq=0, copy_notes=0)
	project = frappe.db.get_value("Awarded Quotation", a.name, "project")
	with as_user("pm"):
		w = frappe.get_doc({"doctype": "WBS", "wbs_code": ROOT, "wbs_name": "Committee wing refurbishment", "project": project,
		                    "node_type": "WBS", "status": "Active", "is_group": 0})
		w.flags.ignore_permissions = True
		w.insert()
	p = frappe._dict(name=project)
	frappe.db.set_value("Awarded Quotation", a.name, {"project": p.name, "status": "In Progress"})
	return a.name, p.name


def certificate(award, lines, start, end, quantities, sent, certified):
	with as_user("qs"):
		ipc = frappe.get_doc({"doctype": "Client IPC", "awarded_quotation": award, "period_from": day(start), "period_to": day(end),
		                      "items": [dict(l) for l in lines]})
		for row in ipc.items:
			row.this_period_qty = next((v for k, v in quantities.items() if row.description.startswith(k)), 0)
		ipc.items = [r for r in ipc.items if r.this_period_qty or r.previous_qty]
		ipc.flags.ignore_permissions = True
		ipc.insert()
		ipc.status = "Submitted to Client"
		ipc.save()
		if certified is not None:
			ipc.submit()
	frappe.db.set_value("Client IPC", ipc.name, {"submitted_on": day(sent), "creation": at(sent, 10),
	                                             "modified": at(certified if certified is not None else sent, 15)}, update_modified=False)
	return ipc.name


def performance_bond(award, project):
	if not frappe.db.exists("Bank", "Rawbank"):
		frappe.get_doc({"doctype": "Bank", "bank_name": "Rawbank"}).insert(ignore_permissions=True)
	value = frappe.db.get_value("Awarded Quotation", award, "contract_value")
	with as_user("finance"):
		bg = frappe.get_doc({"doctype": "Bank Guarantee", "bg_type": "Providing", "customer": CUSTOMER, "project": project,
		                     "reference_doctype": "Awarded Quotation", "reference_docname": award, "bank": "Rawbank",
		                     "name_of_beneficiary": CUSTOMER, "bank_guarantee_number": "RAW-PB-2026-073",
		                     "amount": round(value * 0.10, 2), "start_date": day(-105), "end_date": day(18),
		                     "more_information": "Performance bond, 10% of the contract, valid to the planned completion; extend if the job runs over."})
		bg.flags.ignore_permissions = True
		bg.insert(); bg.submit()
	return bg.name


def emergency_milestones():
	award = frappe.db.get_value("Awarded Quotation", {"title": EMERGENCY}, "name")
	if not award or frappe.db.exists("Awarded Quotation Milestone", {"parent": award}):
		return None
	with as_user("pm"):
		a = frappe.get_doc("Awarded Quotation", award)
		a.append("milestones", {"milestone": "Temporary waterproofing over the debating chamber", "planned_start": day(-2), "planned_end": day(-1),
		                        "actual_end": day(-1), "status": "Completed", "weightage": 20, "billing_percent": 40})
		a.append("milestones", {"milestone": "Membrane and rainwater outlets replaced", "planned_start": day(4), "planned_end": day(34),
		                        "status": "Not Started", "weightage": 80, "billing_percent": 60})
		a.flags.ignore_permissions = True
		a.save()
	comment("Awarded Quotation", award, "Chamber is dry: temporary sheeting done last night. 40% can be billed.", "pm", at(-1, 18))
	return f"{award}: temporary waterproofing done, 40% due"
