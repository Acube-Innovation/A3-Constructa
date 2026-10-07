# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 13.2 and 11.4: a BOQ quantity from approval to the works.

Shared by the Quantity Chain and BOQ vs Consumption reports. Everything is in
the item's stock unit, because that is what every buying and stock document
keeps: a BOQ line in its own unit is converted with the item's UOM conversion
factor before it is compared with anything.

A BOQ line is split into parts, one per WBS it was allocated to by a submitted
WBS Allocation (each part on the allocation's cost code), plus whatever is not
allocated, which stays on the line's own WBS and cost code. Requests, orders
and receipts are traced from the BOQ line through the Material Request line,
whose WBS says which part they buy (api/boq_procurement.py). Material issued
to the works is a Material Issue stock entry (MIN), matched by project, item
and WBS or cost code; a tool written off is a loss, not consumption, so it is
left out.
"""

import frappe
from frappe.utils import flt

from a3_constructa.api.boq_procurement import approved_boqs, boq_lines, progress_by_wbs

NOT_CONSUMPTION = ("Tool Write-off",)


def boq_parts(company=None, project=None, boq=None):
	"""Every approved BOQ line split into its WBS parts, in stock units.

	Returns a list of dicts: project, boq, boq_item, item_code, item_name, stock_uom,
	wbs, cost_code, qty (the part's approved qty), allocated (the share placed by a
	WBS Allocation; 0 for the unallocated rest), wastage_percent, allowed.
	"""
	boqs = approved_boqs(project=project, company=company)
	if boq:
		boqs = [b for b in boqs if b == boq]
	lines = boq_lines(boqs)
	allocations = {}
	if lines:
		for row in frappe.get_all(
			"WBS Allocation Item",
			filters={"boq_item": ["in", [l["boq_item"] for l in lines]], "docstatus": 1},
			fields=["boq_item", "parent", "cost_code", "allocated_qty"],
		):
			allocations.setdefault(row.boq_item, []).append(row)
		wbs_of = dict(frappe.get_all("WBS Allocation", filters={"name": ["in", list({a.parent for v in allocations.values() for a in v})]},
		                             fields=["name", "wbs"], as_list=True))
	parts = []
	for line in lines:
		factor = flt(line["conversion_factor"]) or 1
		base = {"project": line["project"], "boq": line["boq"], "boq_item": line["boq_item"], "item_code": line["item_code"],
		        "item_name": line["item_name"], "stock_uom": line["stock_uom"] or line["uom"], "wastage_percent": line["wastage_percent"]}
		placed = 0.0
		for a in allocations.get(line["boq_item"], []):
			qty = flt(a.allocated_qty) * factor
			placed += qty
			parts.append({**base, "wbs": wbs_of.get(a.parent), "cost_code": a.cost_code or line["cost_code"], "qty": qty, "allocated": qty})
		rest = flt(line["approved_qty"] * factor - placed, 6)
		if rest > 1e-6 or not allocations.get(line["boq_item"]):
			parts.append({**base, "wbs": line["wbs"], "cost_code": line["cost_code"], "qty": max(rest, 0), "allocated": 0.0})
	for part in parts:
		part["allowed"] = part["qty"] * (1 + flt(part["wastage_percent"]) / 100)
	return parts


def buying(parts):
	"""Requested (submitted and draft), ordered and received per (boq_item, wbs), stock units."""
	return progress_by_wbs(list({p["boq_item"] for p in parts}))


def issues(company=None, project=None, to_date=None, item_code=None):
	"""Material issued to the works: rows of project, item_code, wbs, cost_code, qty
	(stock units) and value (its cost at issue)."""
	conditions = ["se.docstatus = 1", "se.purpose = 'Material Issue'",
	              "ifnull(se.stock_entry_type, '') not in %(skip)s", "ifnull(coalesce(sed.project, se.project), '') != ''"]
	values = {"skip": NOT_CONSUMPTION}
	if company:
		conditions.append("se.company = %(company)s")
		values["company"] = company
	if project:
		conditions.append("coalesce(sed.project, se.project) = %(project)s")
		values["project"] = project
	if to_date:
		conditions.append("se.posting_date <= %(to_date)s")
		values["to_date"] = to_date
	if item_code:
		conditions.append("sed.item_code = %(item_code)s")
		values["item_code"] = item_code
	return frappe.db.sql(
		f"""
		select coalesce(sed.project, se.project) as project, sed.item_code, sed.wbs, sed.cost_code,
		       sum(sed.transfer_qty) as qty, sum(sed.amount) as value
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent
		where {" and ".join(conditions)}
		group by 1, 2, 3, 4
		""",
		values,
		as_dict=True,
	)


def project_stock(projects):
	"""What the project's own stores hold, per (project, item), in stock units."""
	if not projects:
		return {}
	stock = {}
	for row in frappe.db.sql(
		"""
		select wh.project, bin.item_code, sum(bin.actual_qty) as qty
		from `tabBin` bin inner join `tabWarehouse` wh on wh.name = bin.warehouse
		where wh.project in %(projects)s
		group by 1, 2
		""",
		{"projects": list(projects)},
		as_dict=True,
	):
		stock[(row.project, row.item_code)] = flt(row.qty)
	return stock
