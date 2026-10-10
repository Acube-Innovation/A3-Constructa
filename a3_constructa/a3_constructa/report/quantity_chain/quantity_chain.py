# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Quantity Chain - catalogue 13.2.

Per project, item and WBS, in the item's stock unit: the approved BOQ quantity,
what WBS Allocation placed, what was requested, ordered and received for it,
what was issued to the works, and (per item) what the project's stores hold.
A tree: Project → Item → WBS. Quantities of different items are never added,
so a project row carries no figures.

The stage filter keeps the WBS rows at one point of the chain: still to
request, requested but not ordered, ordered but not received, requested beyond
the BOQ, or issued beyond the BOQ plus its wastage allowance.

An item that is not in any approved BOQ of the project shows when it was
issued to a WBS: it was used in the works but never budgeted. Issues with no
WBS (fuel for plant) are running costs, not BOQ material, and are left out.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.api.quantity_chain import boq_parts, buying, issues, project_stock

EPS = 1e-6
FIGURES = ("boq_qty", "allowed_qty", "allocated_qty", "requested_qty", "draft_qty", "ordered_qty", "received_qty", "issued_qty")
STAGES = {
	"To request": lambda r: r["boq_qty"] - r["requested_qty"] - r["draft_qty"] > EPS,
	"To order": lambda r: r["requested_qty"] - r["ordered_qty"] > EPS,
	"To receive": lambda r: r["ordered_qty"] - r["received_qty"] > EPS,
	"Over-requested": lambda r: r["requested_qty"] + r["draft_qty"] - r["boq_qty"] > EPS,
	"Over-issued": lambda r: r["issued_qty"] - r["allowed_qty"] > EPS,
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frappe.has_permission("BOQ", "read", throw=True)
	rows = build(filters)
	return columns(), rows


def build(filters):
	parts = boq_parts(filters.company, filters.project, filters.boq)
	if filters.item_code:
		parts = [p for p in parts if p["item_code"] == filters.item_code]
	bought = buying(parts)

	wbs_rows = {}

	def row(project, item, wbs, name=None, uom=None):
		key = (project, item, wbs)
		if key not in wbs_rows:
			wbs_rows[key] = {"project": project, "item_code": item, "item_name": name, "wbs": wbs, "stock_uom": uom,
			                 "boq_items": set(), **{f: 0.0 for f in FIGURES}}
		r = wbs_rows[key]
		r["item_name"] = r["item_name"] or name
		r["stock_uom"] = r["stock_uom"] or uom
		return r

	for p in parts:
		r = row(p["project"], p["item_code"], p["wbs"], p["item_name"], p["stock_uom"])
		r["boq_qty"] += p["qty"]
		r["allowed_qty"] += p["allowed"]
		r["allocated_qty"] += p["allocated"]
		r["boq_items"].add(p["boq_item"])
	# Requests, orders and receipts land on the WBS of the request line.
	line_of = {p["boq_item"]: p for p in parts}
	for (boq_item, wbs), done in bought.items():
		p = line_of[boq_item]
		r = row(p["project"], p["item_code"], wbs, p["item_name"], p["stock_uom"])
		r["requested_qty"] += done.requested
		r["draft_qty"] += done.draft
		r["ordered_qty"] += done.ordered
		r["received_qty"] += done.received
	in_boq = {(p["project"], p["item_code"]) for p in parts}
	projects = {p["project"] for p in parts} | ({filters.project} if filters.project else set())
	for i in issues(filters.company, filters.project, filters.to_date, filters.item_code):
		if filters.boq and (i.project, i.item_code) not in in_boq:
			continue
		if (i.project, i.item_code) not in in_boq and not i.wbs:
			continue  # plant fuel and the like: not BOQ material
		row(i.project, i.item_code, i.wbs)["issued_qty"] += flt(i.qty)
		projects.add(i.project)
	stock = project_stock(projects)

	# Names and units for items only issued, never in a BOQ.
	missing = {r["item_code"] for r in wbs_rows.values() if not r["stock_uom"] or not r["item_name"]}
	if missing:
		for item in frappe.get_all("Item", filters={"name": ["in", list(missing)]}, fields=["name", "item_name", "stock_uom"]):
			for r in wbs_rows.values():
				if r["item_code"] == item.name:
					r["item_name"] = r["item_name"] or item.item_name
					r["stock_uom"] = r["stock_uom"] or item.stock_uom

	for r in wbs_rows.values():
		r["in_boq"] = (r["project"], r["item_code"]) in in_boq
		r["stages"] = [s for s, test in STAGES.items() if test(r)]
		r["to_issue"] = r["received_qty"] - r["issued_qty"] > EPS and "Over-issued" not in r["stages"]
		r["to_request_qty"] = max(0.0, r["boq_qty"] - r["requested_qty"] - r["draft_qty"])
		r["over_issued_qty"] = max(0.0, r["issued_qty"] - r["allowed_qty"])

	shown = [r for r in wbs_rows.values() if not filters.stage or filters.stage in r["stages"]]
	if filters.hide_complete:
		shown = [r for r in shown if r["stages"] or r["issued_qty"] + EPS < r["boq_qty"]]

	project_names = dict(frappe.get_all("Project", filters={"name": ["in", list(projects)]}, fields=["name", "project_name"], as_list=True))
	out = []
	for project in sorted({r["project"] for r in shown}):
		out.append({"key": project, "parent_key": None, "indent": 0, "level": "Project", "project": project,
		            "label": f"{project}: {project_names.get(project) or ''}"})
		items = sorted({r["item_code"] for r in shown if r["project"] == project})
		for item in items:
			children = sorted((r for r in shown if r["project"] == project and r["item_code"] == item), key=lambda r: r["wbs"] or "~")
			every = [r for r in wbs_rows.values() if r["project"] == project and r["item_code"] == item]
			first = every[0]
			ikey = f"{project}|{item}"
			total = {f: sum(r[f] for r in every) for f in FIGURES}
			out.append({"key": ikey, "parent_key": project, "indent": 1, "level": "Item", "project": project, "item_code": item,
			            "label": f"{item}: {first['item_name'] or ''}", "stock_uom": first["stock_uom"], **total,
			            "in_stock_qty": stock.get((project, item), 0.0), "in_boq": first["in_boq"],
			            "stage": ", ".join(s for s in STAGES if STAGES[s](total))
			            or (_("To issue") if total["received_qty"] - total["issued_qty"] > EPS else _("Complete") if total["boq_qty"] else ""),
			            "drill": {"project": project, "item_code": item}})
			for r in children:
				out.append({"key": f"{ikey}|{r['wbs'] or ''}", "parent_key": ikey, "indent": 2, "level": "WBS", "project": project,
				            "item_code": item, "wbs": r["wbs"], "stock_uom": r["stock_uom"], "in_boq": r["in_boq"],
				            "label": r["wbs"] or _("No WBS"), **{f: r[f] for f in FIGURES},
				            "stage": ", ".join(r["stages"]) or (_("To issue") if r["to_issue"] else _("Complete") if r["boq_qty"] else ""),
				            "flag": "Over-issued" in r["stages"] or "Over-requested" in r["stages"] or (not r["in_boq"]),
				            "drill": {"project": project, "item_code": item, "wbs": r["wbs"]}})
	return out


def columns():
	q = lambda name, label, width=110: {"fieldname": name, "label": label, "fieldtype": "Float", "width": width, "precision": 3}
	return [
		{"fieldname": "label", "label": _("Project / Item / WBS"), "fieldtype": "Data", "width": 300},
		{"fieldname": "stock_uom", "label": _("Stock Unit"), "fieldtype": "Link", "options": "UOM", "width": 100},
		q("boq_qty", _("BOQ Qty")),
		q("allowed_qty", _("Allowed (with wastage)"), 130),
		q("allocated_qty", _("Allocated")),
		q("requested_qty", _("Requested")),
		q("ordered_qty", _("Ordered")),
		q("received_qty", _("Received")),
		q("issued_qty", _("Issued")),
		q("in_stock_qty", _("In Project Stores"), 120),
		{"fieldname": "stage", "label": _("Stage"), "fieldtype": "Data", "width": 220},
	]
