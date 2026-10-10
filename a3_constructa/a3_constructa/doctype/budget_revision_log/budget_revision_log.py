# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget Revision Log - catalogue 1.6.

One row per change to the budget of a WBS node and cost code: the original BOQ,
each BOQ revision, approved variations, and transfers in and out. The system
writes it through `revise_budget`; users only read it, so the revised budget of
any node is the sum of its rows and every change can be traced to a document.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

CHANGE_TYPES = ("Original", "BOQ Revision", "Variation", "Transfer In", "Transfer Out")


class BudgetRevisionLog(Document):
	def validate(self):
		if not self.flags.from_revise_budget:
			frappe.throw(_("The Budget Revision Log is written by the system. Change a budget through a BOQ, a Variation Order or a Budget Transfer."))

	def on_trash(self):
		# Administrator may still clear a demo or test site.
		if frappe.session.user == "Administrator":
			return
		frappe.throw(_("Budget Revision Log rows cannot be deleted. Cancel the document that wrote them instead."))


def revise_budget(project, wbs, cost_code, amount, change_type, reference, reason=None, posted_on=None, posted_by=None):
	"""Record one change to the budget of `wbs` / `cost_code` on `project`.

	`reference` is the document that made the change, as a Document or a
	(doctype, name) pair. A positive amount adds budget, a negative one takes it
	away; a zero amount writes nothing. P-03B calls this for approved variations
	with change_type "Variation".
	"""
	if change_type not in CHANGE_TYPES:
		frappe.throw(_("Unknown budget change type {0}.").format(change_type))
	amount = flt(amount, 2)
	if not amount:
		return None
	ref_doctype, ref_name = (reference.doctype, reference.name) if hasattr(reference, "doctype") else reference

	row = frappe.get_doc({
		"doctype": "Budget Revision Log",
		"project": project,
		"wbs": wbs,
		"cost_code": cost_code,
		"change_type": change_type,
		"amount": amount,
		"reference_doctype": ref_doctype,
		"reference_name": ref_name,
		"posted_on": posted_on or now_datetime(),
		"posted_by": posted_by or frappe.session.user,
		"reason": reason,
	})
	row.flags.from_revise_budget = True
	row.flags.ignore_permissions = True
	row.insert()
	return row


def logged_by_line(project, references):
	"""Net logged amount per (wbs, cost_code) for the given (doctype, name) references."""
	if not references:
		return {}
	out = {}
	for doctype, name in references:
		for r in frappe.get_all(
			"Budget Revision Log",
			filters={"project": project, "reference_doctype": doctype, "reference_name": name},
			fields=["wbs", "cost_code", "sum(amount) as amount"],
			group_by="wbs, cost_code",
		):
			key = (r.wbs, r.cost_code)
			out[key] = out.get(key, 0) + flt(r.amount)
	return out
