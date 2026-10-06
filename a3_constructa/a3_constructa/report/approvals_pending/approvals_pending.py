# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Approvals Pending - catalogue 9.3.

Every Material Request and Purchase Order still waiting for an approval level:
which level, who gives it, how far it has got, and how many days it has waited
since it was raised or last approved. A rejected document waits for its
requester, not an approver, and is shown as such.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, getdate, nowdate

from a3_constructa.overrides.approvals import DOCTYPES, can_approve, describe, document_value, matrix_rows, next_level


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = []
	for doctype in DOCTYPES:
		if filters.get("document_type") and filters.document_type != doctype:
			continue
		if not frappe.has_permission(doctype, "read"):
			continue
		conditions = {"docstatus": 0, "approval_level_required": [">", 0]}
		if filters.get("company"):
			conditions["company"] = filters.company
		for name in frappe.get_list(doctype, filters=conditions, pluck="name", order_by="creation"):
			doc = frappe.get_doc(doctype, name)
			rows = matrix_rows(doc)
			level, approvers = next_level(doc, rows)
			last = doc.approvals[-1] if doc.approvals else None
			rejected = bool(last and last.action == "Rejected" and not cint(doc.approval_level_reached))
			if not level and not rejected:
				continue
			mine = bool(level) and not rejected and can_approve(approvers) and doc.owner != frappe.session.user
			if filters.get("mine") and not mine:
				continue
			since = getdate(last.on) if last else getdate(doc.creation)
			data.append({
				"document_type": doctype,
				"document": name,
				"project": doc.get("project") or next((r.project for r in doc.items if r.get("project")), None),
				"value": document_value(doc),
				"status": _("Rejected, back with the requester") if rejected else _("Waiting for level {0}").format(level),
				"next_level": None if rejected else level,
				"approver": frappe.utils.get_fullname(doc.owner) if rejected else describe(approvers),
				"progress": f"{cint(doc.approval_level_reached)} / {cint(doc.approval_level_required)}",
				"waiting_since": since,
				"age_days": date_diff(nowdate(), since),
				"raised_by": frappe.utils.get_fullname(doc.owner),
				"is_rejected": int(rejected),
				"is_mine": int(mine),
			})
	data.sort(key=lambda r: -r["age_days"])
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "document", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "document_type", "width": 200},
		{"fieldname": "document_type", "label": _("Type"), "fieldtype": "Data", "width": 125},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 250},
		{"fieldname": "approver", "label": _("Next Approver"), "fieldtype": "Data", "width": 190},
		{"fieldname": "progress", "label": _("Levels Done"), "fieldtype": "Data", "width": 100},
		{"fieldname": "age_days", "label": _("Waiting (days)"), "fieldtype": "Int", "width": 115},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "raised_by", "label": _("Raised By"), "fieldtype": "Data", "width": 140},
		{"fieldname": "waiting_since", "label": _("Waiting Since"), "fieldtype": "Date", "width": 110},
	]
