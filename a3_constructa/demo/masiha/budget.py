# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-01C: budget revisions and transfers.

The flooring BOQ's revision gets the reason the QS gave for it, so the Budget
Revision Log reads as the story did. Four Budget Transfers move money between
WBS nodes, one in each state: two submitted, one submitted and then cancelled,
and one draft awaiting approval.
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, at, comment, day, insert, log, project

FLOORING_REVISION_REASON = "Revised after design development: tile budget to $18.50/m2, adhesive to $9.80, grout added."

# (key, transfer day, reason, [(from wbs, from code, to wbs, to code, amount)], final state)
TRANSFERS = [
	("doors", -40, "Two extra fire-rated doors for the plant room, paid from MEP cable savings.",
	 [("MSS-W-MEP", "MSS-CC-MEP-M", "MSS-W-DW", "MSS-CC-DW-M", 1200)], "submitted"),
	("wastage", -30, "Ground-floor tile wastage came in under the allowance; the saving covers first-floor cuts.",
	 [("MSS-W-FL-A", "MSS-CC-FIN-M", "MSS-W-FL-B", "MSS-CC-FIN-M", 300)], "submitted"),
	("skirting", -25, "Porcelain skirting on the first floor, paid from painting.",
	 [("MSS-W-PT", "MSS-CC-PNT-M", "MSS-W-FL-B", "MSS-CC-FIN-M", 800)], "cancelled"),
	("containment", -5, "Extra cable containment for the data network. Awaiting the project manager's approval.",
	 [("MSS-W-ES", "MSS-CC-STR-M", "MSS-W-MEP", "MSS-CC-MEP-M", 5000),
	  ("MSS-W-ES", "MSS-CC-STR-M", "MSS-W-DW", "MSS-CC-DW-M", 1500)], "draft"),
]


def run():
	record_revision_reason()
	create_transfers()


def record_revision_reason():
	for name in frappe.get_all("BOQ", filters={"project": project(), "amended_from": ["is", "set"], "docstatus": 1}, pluck="name"):
		boq = frappe.get_doc("BOQ", name)
		if boq.cost_head != "MSS-AR-FL" or (boq.revision_reason and "before revision reasons" not in boq.revision_reason):
			continue
		boq.db_set("revision_reason", FLOORING_REVISION_REASON, update_modified=False)
		for row in frappe.get_all("Budget Revision Log", filters={"reference_doctype": "BOQ", "reference_name": name}, pluck="name"):
			frappe.db.set_value("Budget Revision Log", row, "reason",
			                    f"Revision {boq.revision_no}: {FLOORING_REVISION_REASON}", update_modified=False)
		log(f"{name}: revision reason recorded")


def create_transfers():
	if frappe.db.exists("Budget Transfer", {"project": project()}):
		log("budget transfers already present")
		return
	made = []
	for key, when, reason, lines, state in TRANSFERS:
		with as_user("qs"):
			bt = insert({
				"doctype": "Budget Transfer", "project": project(), "transfer_date": day(when), "reason": reason,
				"items": [{"from_wbs": f, "from_cost_code": fc, "to_wbs": t, "to_cost_code": tc, "amount": amount}
				          for f, fc, t, tc, amount in lines],
			})
		if state in ("submitted", "cancelled"):
			with as_user("pm"):
				bt.submit()
			date_log_rows(bt.name, at(when, 15))
		if state == "cancelled":
			with as_user("pm"):
				bt.reload()
				bt.flags.ignore_permissions = True
				bt.cancel()
			date_log_rows(bt.name, at(when + 3, 10), cancelled=True)
			comment("Budget Transfer", bt.name, "Cancelled: the painting take-off was wrong, the skirting is in the flooring BOQ already.", "pm", at(when + 3, 10))
		made.append(f"{bt.name} {state}")
	log("budget transfers: " + ", ".join(made))


def date_log_rows(name, when, cancelled=False):
	"""Put the log rows on the story day rather than today."""
	rows = frappe.get_all("Budget Revision Log", filters={"reference_doctype": "Budget Transfer", "reference_name": name},
	                      fields=["name", "reason"], order_by="creation")
	for row in rows:
		if cancelled == (row.reason or "").startswith("Cancelled"):
			frappe.db.set_value("Budget Revision Log", row.name, "posted_on", when, update_modified=False)
