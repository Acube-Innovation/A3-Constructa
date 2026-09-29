# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Put every document of the story, and its timeline, on the story's calendar.

The story is built in one sitting, so everything ERPNext stamps by itself (a
document's creation, a status label, an assignment note) carries today's time,
while the approvals and comments carry their story dates. A timeline that shows
an approval months before its document was created would undercut step 6.

Each document's creation moves to its own story date. Each automatic timeline
entry moves to the story date of the document that caused it: the one created
just before it, in the order the build actually ran (a status label on the
flooring request lands on the cash bill that changed it). Only rows still
stamped today are touched, so re-running changes nothing.
"""

import frappe
from frappe.utils import add_to_date, get_datetime, getdate, nowdate

from a3_constructa.demo.masiha.common import COMPANY, log, project

# Where each doctype keeps the date it happened on.
STORY_DATE = {
	"Journal Entry": "posting_date",
	"Project": "expected_start_date",
	"BOQ": "boq_date",
	"Awarded Quotation": "award_date",
	"Sales Order": "transaction_date",
	"Procurement Plan": "plan_date",
	"Variation Order": "vo_date",
	"Material Request": "transaction_date",
	"Request for Quotation": "transaction_date",
	"Supplier Quotation": "transaction_date",
	"Purchase Order": "transaction_date",
	"Payment Entry": "posting_date",
	"Shipment Tracking": "asn_date",
	"Purchase Receipt": "posting_date",
	"Purchase Invoice": "posting_date",
	"Landed Cost Voucher": "posting_date",
	"Stock Entry": "posting_date",
	"Asset": "available_for_use_date",
	"Asset Movement": "transaction_date",
	"Sales Invoice": "posting_date",
}


def run():
	today = getdate(nowdate())
	anchors = _anchors()
	moved_docs = moved_rows = 0

	for doctype, name, real, story in anchors:
		if getdate(real) == today:
			frappe.db.set_value(doctype, name, {"creation": story, "modified": story}, update_modified=False)
			moved_docs += 1

	names = {(d, n) for d, n, _r, _s in anchors}
	for table, ref_type, ref_name in (("Comment", "reference_doctype", "reference_name"),
	                                  ("Version", "ref_doctype", "docname"),
	                                  ("ToDo", "reference_type", "reference_name")):
		for row in frappe.get_all(table, filters={"creation": [">=", nowdate()]},
		                          fields=["name", "creation", ref_type, ref_name]):
			if (row[ref_type], row[ref_name]) not in names:
				continue
			frappe.db.set_value(table, row.name, {"creation": _warp(row.creation, anchors),
			                                      "modified": _warp(row.creation, anchors)}, update_modified=False)
			moved_rows += 1

	_order_labels_and_assignments(names)
	frappe.db.commit()
	log(f"timeline: {moved_docs} documents and {moved_rows} timeline entries put on the story calendar")


def _order_labels_and_assignments(names):
	"""Two rules the build order cannot express on its own.

	A status label ("Pending", "To Receive and Bill") comes from the submit, so it
	never precedes the approval that submitted the document. An "assigned" note
	sits with the assignment it records.
	"""
	for c in frappe.get_all("Comment", filters={"comment_type": ["in", ["Label", "Assigned"]]},
	                        fields=["name", "comment_type", "creation", "reference_doctype", "reference_name", "content"]):
		if (c.reference_doctype, c.reference_name) not in names:
			continue
		if c.comment_type == "Label":
			approved = frappe.db.get_value("Comment", {"reference_doctype": c.reference_doctype,
			                                           "reference_name": c.reference_name, "comment_type": "Workflow",
			                                           "content": "Approved"}, "creation")
			if approved and c.creation < approved:
				when = add_to_date(approved, minutes=1)
				frappe.db.set_value("Comment", c.name, {"creation": when, "modified": when}, update_modified=False)
		else:
			todo = frappe.db.get_value("ToDo", {"reference_type": c.reference_doctype,
			                                    "reference_name": c.reference_name}, "creation", order_by="creation")
			if todo and abs((c.creation - todo).total_seconds()) > 60:
				when = add_to_date(todo, seconds=1)
				frappe.db.set_value("Comment", c.name, {"creation": when, "modified": when}, update_modified=False)


def _anchors() -> list[tuple]:
	"""(doctype, name, real creation, story time) for every story document, in build order."""
	rows = []
	for doctype, field in STORY_DATE.items():
		filters = _story_filters(doctype)
		for doc in frappe.get_all(doctype, filters=filters, fields=["name", "creation", field]):
			when = doc.get(field)
			if not when:
				continue
			story = get_datetime(when) if " " in str(when) else get_datetime(f"{when} 08:30:00")
			rows.append((doctype, doc.name, doc.creation, story))
	return sorted(rows, key=lambda r: r[2])


def _story_filters(doctype: str) -> dict:
	meta = frappe.get_meta(doctype)
	if meta.has_field("company"):
		return {"company": COMPANY}
	if doctype == "Project":
		return {"name": project()}
	if meta.has_field("project"):
		return {"project": project()}
	if doctype == "Variation Order":
		return {"awarded_quotation": ["in", frappe.get_all("Awarded Quotation", {"company": COMPANY}, pluck="name")]}
	return {"name": ["is", "not set"]}


def _warp(real, anchors):
	"""The story time of whatever was created just before `real`, plus the same small gap."""
	before = [a for a in anchors if a[2] <= real]
	if not before:
		return real
	_doctype, _name, anchor_real, anchor_story = before[-1]
	gap = min((real - anchor_real).total_seconds(), 3600)
	return add_to_date(anchor_story, seconds=gap)
