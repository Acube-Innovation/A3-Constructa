# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Budget Revision Log - catalogue 1.6.

Per WBS node and cost code, side by side: the original budget, BOQ revisions,
variations, transfers in and out, and the revised budget they add up to. Every
figure links to the log rows behind it.
"""

import frappe
from frappe import _
from frappe.utils import flt

COLUMNS = {
	"Original": "original",
	"BOQ Revision": "boq_revision",
	"Variation": "variation",
	"Transfer In": "transfer_in",
	"Transfer Out": "transfer_out",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions, values = ["1 = 1"], {}
	if filters.get("project"):
		conditions.append("log.project = %(project)s")
		values["project"] = filters.project
	if filters.get("company"):
		conditions.append("log.project in (select name from `tabProject` where company = %(company)s)")
		values["company"] = filters.company
	if filters.get("wbs"):
		from a3_constructa.api.budget_allocation import wbs_subtree

		conditions.append("log.wbs in %(nodes)s")
		values["nodes"] = wbs_subtree(filters.wbs)
	if filters.get("cost_code"):
		conditions.append("log.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code

	rows = frappe.db.sql(
		"""
		select log.project, log.wbs, log.cost_code, log.change_type, sum(log.amount) as amount, count(*) as entries
		from `tabBudget Revision Log` log
		left join `tabWBS` wbs on wbs.name = log.wbs
		where {conditions}
		group by log.project, log.wbs, log.cost_code, log.change_type
		order by log.project, wbs.lft, log.cost_code
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	names = dict(frappe.get_all("WBS", fields=["name", "wbs_name"], as_list=True))
	data, index = [], {}
	for r in rows:
		key = (r.project, r.wbs, r.cost_code)
		if key not in index:
			index[key] = len(data)
			data.append({"project": r.project, "wbs": r.wbs, "wbs_name": names.get(r.wbs), "cost_code": r.cost_code,
			             **{f: 0.0 for f in COLUMNS.values()}, "revised": 0.0, "entries": 0})
		row = data[index[key]]
		row[COLUMNS[r.change_type]] += flt(r.amount)
		row["revised"] += flt(r.amount)
		row["entries"] += r.entries
	return get_columns(), data


def get_columns():
	money = lambda field, label: {"fieldname": field, "label": label, "fieldtype": "Currency", "width": 118}
	return [
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 115},
		{"fieldname": "wbs_name", "label": _("WBS Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link", "options": "Cost Code", "width": 125},
		money("original", _("Original")),
		money("boq_revision", _("BOQ Revisions")),
		money("variation", _("Variations")),
		money("transfer_in", _("Transfers In")),
		money("transfer_out", _("Transfers Out")),
		money("revised", _("Revised Budget")),
		{"fieldname": "entries", "label": _("Log Rows"), "fieldtype": "Int", "width": 75},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
	]
