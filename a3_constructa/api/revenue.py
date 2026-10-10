# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 13.4: revenue earned on a job, by WBS and by award.

Revenue is what the client has certified: the lines of each submitted Client IPC
(Certified or Invoiced) whose period ends by the date, each on its WBS, plus the
materials on site it certified (no WBS). An award billed by milestones has no
certificates; its invoices to the client count instead, line by line on their
WBS, leaving out advance invoices (money in advance, not revenue), retention
releases (revenue certified earlier) and the invoices an IPC already made.

Billed to date is every invoice to the client on the award up to the date, net
of tax, except advance invoices and retention releases (credit notes reduce it).
"""

from collections import defaultdict

import frappe
from frappe.utils import flt


def certified_revenue(project, as_on):
	"""{wbs or None: amount} certified by the client up to `as_on`, and the
	certificates it came from."""
	revenue = defaultdict(float)
	ipcs = frappe.get_all("Client IPC", filters={"project": project, "docstatus": 1, "status": ["in", ["Certified", "Invoiced"]],
	                                              "period_to": ["<=", as_on]},
	                      fields=["name", "materials_on_site"])
	if ipcs:
		for line in frappe.get_all("Client IPC Item", filters={"parent": ["in", [i.name for i in ipcs]], "parenttype": "Client IPC"},
		                           fields=["wbs", "this_period_amount"]):
			revenue[line.wbs or None] += flt(line.this_period_amount)
		for i in ipcs:
			revenue[None] += flt(i.materials_on_site)
	return revenue, [i.name for i in ipcs]


def invoiced_revenue(project, as_on):
	"""{wbs or None: amount} from invoices that no certificate stands behind (milestones)."""
	revenue = defaultdict(float)
	for row in frappe.db.sql(
		"""select sii.wbs, sum(sii.base_net_amount) amount
		from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
		where si.docstatus = 1 and si.project = %(project)s and si.posting_date <= %(as_on)s
			and ifnull(si.client_ipc, '') = '' and ifnull(si.is_advance_invoice, 0) = 0
			and ifnull(si.is_retention_release, 0) = 0 and ifnull(si.final_account, '') = ''
			and ifnull(si.awarded_quotation, '') != ''
			and si.name not in (select ifnull(sales_invoice, '') from `tabClient IPC` where docstatus = 1)
			and si.name not in (select ifnull(opening_invoice, '') from `tabClient IPC` where docstatus = 1)
		group by sii.wbs""",
		{"project": project, "as_on": as_on},
		as_dict=True,
	):
		revenue[row.wbs or None] += flt(row.amount)
	return revenue


def billed_to_date(award, as_on):
	return flt(frappe.db.sql(
		"""select sum(base_net_total) from `tabSales Invoice`
		where docstatus = 1 and awarded_quotation = %(award)s and posting_date <= %(as_on)s
			and ifnull(is_advance_invoice, 0) = 0 and ifnull(is_retention_release, 0) = 0""",
		{"award": award, "as_on": as_on},
	)[0][0])
