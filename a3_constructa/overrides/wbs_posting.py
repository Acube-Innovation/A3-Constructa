# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 1.2: only an Active WBS node accepts postings.

Hooked on validate of Material Request, Purchase Order, Stock Entry, Timesheet,
WBS Allocation and Variation Order, so a Draft node cannot be booked to before
it is opened, and an On Hold or Completed one cannot be booked to after it is
stopped. The check reads the WBS on the document itself and on every line.
"""

import frappe
from frappe import _


def validate_active_wbs(doc, method=None):
	used = {}  # wbs -> first row label that uses it
	if doc.meta.has_field("wbs") and doc.get("wbs"):
		used.setdefault(doc.wbs, _("the document"))
	for table in doc.meta.get_table_fields():
		for row in doc.get(table.fieldname) or []:
			if row.get("wbs"):
				used.setdefault(row.wbs, _("row {0}").format(row.idx))
	if not used:
		return

	statuses = dict(frappe.get_all("WBS", filters={"name": ["in", list(used)]}, fields=["name", "status"], as_list=True))
	blocked = [(wbs, where, statuses.get(wbs)) for wbs, where in used.items() if statuses.get(wbs) != "Active"]
	if not blocked:
		return

	lines = "".join(
		"<li>{0}: WBS {1} is {2}</li>".format(where, frappe.bold(wbs), status or _("missing")) for wbs, where, status in blocked
	)
	frappe.throw(
		_("Only Active WBS nodes accept postings. Activate these nodes or pick another WBS:") + f"<ul>{lines}</ul>",
		title=_("WBS not Active"),
	)
