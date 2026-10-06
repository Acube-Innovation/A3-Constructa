# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Quotation Revisions - catalogue 2.7.

Every quotation with its revisions underneath: re-pricing is cancel and amend,
so SAL-QTN-0001, -1, -2 are one quotation issued three times. Each revision
shows its reason, value, change on the one before, margin and approval state;
the group row shows the latest issue and the change since the first.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	chains = get_chains(filters)
	return get_columns(), build_rows(chains), None, None


def get_columns():
	return [
		{"fieldname": "label", "label": _("Quotation / Revision"), "fieldtype": "Data", "width": 200},
		{"fieldname": "quotation", "label": _("Quotation"), "fieldtype": "Link", "options": "Quotation", "width": 165},
		{"fieldname": "client", "label": _("Client"), "fieldtype": "Data", "width": 160},
		{"fieldname": "transaction_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "reason", "label": _("Reason"), "fieldtype": "Data", "width": 240},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Currency", "options": "currency", "width": 130},
		{"fieldname": "change", "label": _("Change vs Previous"), "fieldtype": "Currency", "options": "currency", "width": 140},
		{"fieldname": "margin_percent", "label": _("Margin %"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "approval", "label": _("Approval"), "fieldtype": "Data", "width": 170},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		# A link column needs read access to its doctype, which sales may not have.
		{"fieldname": "boq", "label": _("BOQ"), "width": 120,
		 **({"fieldtype": "Link", "options": "BOQ"} if frappe.has_permission("BOQ", "read") else {"fieldtype": "Data"})},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_chains(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	rows = frappe.get_list(
		"Quotation",
		filters=conditions,
		fields=["name", "amended_from", "revision_no", "revision_reason", "transaction_date", "grand_total", "currency",
		        "margin_percent", "workflow_state", "status", "docstatus", "customer_name", "party_name", "boq"],
		order_by="creation asc",
		limit_page_length=0,
	)
	by_name = {r.name: r for r in rows}

	def root(r):
		seen = set()
		while r.amended_from and r.amended_from in by_name and r.name not in seen:
			seen.add(r.name)
			r = by_name[r.amended_from]
		return r.name

	chains = {}
	for r in rows:
		chains.setdefault(root(r), []).append(r)
	out = []
	for name, revs in chains.items():
		revs.sort(key=lambda r: (r.revision_no or 0, r.name))
		first, latest = revs[0], revs[-1]
		if filters.get("from_date") and str(latest.transaction_date) < str(filters.from_date):
			continue
		if filters.get("to_date") and str(first.transaction_date) > str(filters.to_date):
			continue
		if filters.get("boq") and not any(r.boq == filters.boq for r in revs):
			continue
		if filters.get("only_revised") and len(revs) < 2:
			continue
		out.append((name, revs))
	out.sort(key=lambda c: str(c[1][-1].transaction_date), reverse=True)
	return out


def approval(r, superseded=False):
	"""A cancelled issue that was amended is superseded by the next revision."""
	if r.docstatus == 2:
		return _("Superseded") if superseded else _("Cancelled")
	return _(r.workflow_state or ("Submitted" if r.docstatus == 1 else "Draft"))


def build_rows(chains):
	data = []
	for name, revs in chains:
		first, latest = revs[0], revs[-1]
		data.append({
			"id": name, "parent_id": None, "indent": 0, "is_group": 1,
			"label": name, "client": latest.customer_name or latest.party_name,
			"transaction_date": latest.transaction_date,
			"reason": _("{0} issues").format(len(revs)) if len(revs) > 1 else _("First issue only"),
			"value": latest.grand_total,
			"change": flt(latest.grand_total) - flt(first.grand_total) if len(revs) > 1 else None,
			"margin_percent": latest.margin_percent if latest.boq else None, "approval": approval(latest), "status": _(latest.status),
			"boq": latest.boq, "currency": latest.currency, "quotation": latest.name,
		})
		previous = None
		for r in revs:
			data.append({
				"id": r.name, "parent_id": name, "indent": 1,
				"label": _("Revision {0}").format(r.revision_no or 0), "quotation": r.name,
				"client": r.customer_name or r.party_name, "transaction_date": r.transaction_date,
				"reason": (r.revision_reason or "").strip() or (_("First issue") if not r.amended_from else ""),
				"value": r.grand_total,
				"change": flt(r.grand_total) - flt(previous.grand_total) if previous else None,
				"margin_percent": r.margin_percent if r.boq else None, "approval": approval(r, r is not latest), "status": _(r.status),
				"boq": r.boq, "currency": r.currency,
			})
			previous = r
	return data
