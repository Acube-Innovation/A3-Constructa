# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""BOQ vs Consumption - build sheet head 49 row 23; catalogue 11.4 and 13.2 (P-13B).

What the approved BOQ allows against what has been issued to the works, per
project, WBS, cost code and item (a line split by WBS Allocation is judged
part by part, so over-use on one part of the works is not hidden by another). The over-use flag is the point of the report:
material issued beyond the BOQ quantity plus its wastage allowance is either a
variation to claim or a loss to explain, and somebody needs to see it while
the job is still running.

Every quantity is in the item's stock unit before it is compared: a BOQ line
measured in another unit (tonnes of steel against kilograms in store) is
converted with the item's conversion factor. Allowed = BOQ qty × (1 + the BOQ
line's wastage %). Only approved BOQs count: a draft or tender BOQ is not a
budget. Material issued to a WBS with no BOQ line was never budgeted, so all
of it is over-use; an issue with no WBS of an item no BOQ holds (diesel for
plant) is a running cost, not BOQ material, and is left out. Over-use is valued at what the issued material cost.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.api.quantity_chain import boq_parts, issues

EPS = 1e-6


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frappe.has_permission("BOQ", "read", throw=True)
	return get_columns(), get_data(filters)


def get_data(filters):
	rows = {}

	def row(project, wbs, cost_code, item):
		return rows.setdefault((project, wbs, cost_code, item), {"project": project, "wbs": wbs, "cost_code": cost_code, "item_code": item,
		                                                    "boq_qty": 0.0, "allowed_qty": 0.0, "issued_qty": 0.0, "issued_value": 0.0})

	parts = boq_parts(filters.company, filters.project)
	in_boq = {(p["project"], p["item_code"]) for p in parts}
	for p in parts:
		if not p["cost_code"] or (filters.cost_code and p["cost_code"] != filters.cost_code):
			continue
		r = row(p["project"], p["wbs"], p["cost_code"], p["item_code"])
		r["boq_qty"] += p["qty"]
		r["allowed_qty"] += p["allowed"]
		r["stock_uom"] = p["stock_uom"]
	for i in issues(filters.company, filters.project, filters.to_date):
		if not i.cost_code or (filters.cost_code and i.cost_code != filters.cost_code):
			continue
		if (i.project, i.item_code) not in in_boq and not i.wbs:
			continue  # plant fuel and the like: running costs, not BOQ material
		r = row(i.project, i.wbs, i.cost_code, i.item_code)
		r["issued_qty"] += flt(i.qty)
		r["issued_value"] += flt(i.value)

	uoms = dict(frappe.get_all("Item", filters={"name": ["in", list({r["item_code"] for r in rows.values()})]},
	                           fields=["name", "stock_uom"], as_list=True)) if rows else {}
	data = []
	for r in rows.values():
		r["stock_uom"] = r.get("stock_uom") or uoms.get(r["item_code"])
		r["wastage_percent"] = (r["allowed_qty"] / r["boq_qty"] - 1) * 100 if r["boq_qty"] else 0
		r["balance_qty"] = r["allowed_qty"] - r["issued_qty"]
		r["consumed_percent"] = r["issued_qty"] / r["allowed_qty"] * 100 if r["allowed_qty"] else (100 if r["issued_qty"] else 0)
		r["over_qty"] = max(0.0, r["issued_qty"] - r["allowed_qty"])
		rate = r["issued_value"] / r["issued_qty"] if r["issued_qty"] else 0
		r["over_value"] = r["over_qty"] * rate
		r["over_consumed"] = 1 if r["over_qty"] > EPS else 0
		r["not_in_boq"] = 1 if not r["boq_qty"] else 0
		data.append(r)
	if filters.get("only_over_consumed"):
		data = [r for r in data if r["over_consumed"]]
	data.sort(key=lambda r: (-r["over_consumed"], -r["over_value"], -r["consumed_percent"], r["project"], r["wbs"] or "", r["cost_code"], r["item_code"]))
	return data


def get_columns():
	q = lambda name, label, width=110: {"fieldname": name, "label": label, "fieldtype": "Float", "width": width, "precision": 3}
	return [
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "wbs", "label": _("WBS"), "fieldtype": "Link", "options": "WBS", "width": 120},
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link", "options": "Cost Code", "width": 140},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "stock_uom", "label": _("Stock Unit"), "fieldtype": "Link", "options": "UOM", "width": 100},
		q("boq_qty", _("BOQ Qty")),
		{"fieldname": "wastage_percent", "label": _("Wastage %"), "fieldtype": "Percent", "width": 90},
		q("allowed_qty", _("Allowed")),
		q("issued_qty", _("Issued")),
		q("balance_qty", _("Balance")),
		{"fieldname": "consumed_percent", "label": _("% of Allowed"), "fieldtype": "Percent", "width": 110},
		q("over_qty", _("Over-use Qty")),
		{"fieldname": "over_value", "label": _("Over-use Value"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "over_consumed", "label": _("Over-use"), "fieldtype": "Check", "width": 80},
	]
