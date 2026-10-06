# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""BOQ lines through procurement: approved, requested, ordered, received.

A Material Request line fetched from a BOQ carries `boq` and `boq_item` (custom
fields on Material Request Item). ERPNext already carries the Material Request
line onto the RFQ, Supplier Quotation, Purchase Order and Purchase Receipt as
`material_request_item`, so every later step traces back to the BOQ line it
buys.

Several BOQs can feed one Material Request. That is how the packages of an
award, or of several awards, are bought together: one request, one RFQ, one
order, while each line keeps its own project, cost head, WBS and cost code so
the budget reports still see where the money went.

Quantities are compared in the item's stock UOM, which is what ERPNext keeps on
every buying document, and handed back in the BOQ line's own UOM. The approved
quantity is what may be bought; a line approved without one falls back to its
BOQ quantity.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Everything a line's progress is read from.
TRACE_DOCTYPES = ("BOQ", "Material Request", "Purchase Order", "Purchase Receipt")


def can_trace() -> bool:
	return all(frappe.has_permission(doctype, "read") for doctype in TRACE_DOCTYPES)


@frappe.whitelist()
def get_request_lines(awarded_quotation: str | None = None, project: str | None = None, company: str | None = None):
	"""Approved BOQ lines and what is left to request, for Material Request > Get Items From > BOQ."""
	if not (awarded_quotation or project):
		frappe.throw(_("Choose an awarded quotation or a project."))
	frappe.has_permission("BOQ", "read", throw=True)
	lines = boq_lines(approved_boqs(awarded_quotation, project, company))
	return [public(line) for line in split_by_allocation(lines)]


def split_by_allocation(lines: list[dict]) -> list[dict]:
	"""Offer a BOQ line once per WBS it has been allocated to.

	One BOQ line can be split across the works by WBS Allocation: 1,000 m2 of
	one porcelain tile, 600 to the ground floor and 400 to the first. Each part
	is requested on its own line, with its own WBS and cost code, so the
	commitment and the consumption land on the right part of the works. What is
	left unallocated is offered as one more line on the BOQ line's own WBS.
	"""
	by_line = {}
	for row in frappe.get_list(
		"WBS Allocation",
		filters=[["WBS Allocation Item", "boq_item", "in", [line["boq_item"] for line in lines] or [""]],
		         ["WBS Allocation", "docstatus", "<", 2]],
		fields=[
			"wbs",
			"`tabWBS Allocation Item`.boq_item as boq_item",
			"`tabWBS Allocation Item`.allocated_qty as qty",
			"`tabWBS Allocation Item`.cost_code as cost_code",
		],
		limit_page_length=0,
	):
		by_line.setdefault(row.boq_item, []).append(row)
	if not by_line:
		return lines

	# What has been requested for each part, in the BOQ line's UOM.
	asked = {}
	for row in frappe.get_all(
		"Material Request Item",
		filters={"boq_item": ["in", list(by_line)], "docstatus": ["<", 2]},
		fields=["boq_item", "wbs", "stock_qty", "docstatus"],
	):
		key = (row.boq_item, row.wbs, row.docstatus == 1)
		asked[key] = asked.get(key, 0) + flt(row.stock_qty)

	result = []
	for line in lines:
		allocations = by_line.get(line["boq_item"])
		if not allocations:
			result.append(line)
			continue

		factor = line["conversion_factor"] or 1
		parts = [(a.wbs, a.cost_code or line["cost_code"], flt(a.qty)) for a in allocations]
		unallocated = flt(line["approved_qty"] - sum(qty for _w, _c, qty in parts), 3)
		if unallocated > 0:
			parts.append((line["wbs"], line["cost_code"], unallocated))

		for wbs, cost_code, qty in parts:
			requested = flt(asked.get((line["boq_item"], wbs, True), 0) / factor, 3)
			draft = flt(asked.get((line["boq_item"], wbs, False), 0) / factor, 3)
			result.append(
				{
					**line,
					"wbs": wbs,
					"cost_code": cost_code,
					"approved_qty": qty,
					"requested_qty": requested,
					"draft_qty": draft,
					"to_request": max(0.0, flt(qty - requested - draft, 3)),
					"allocated": True,
				}
			)
	return result


def approved_boqs(awarded_quotation=None, project=None, company=None) -> list[str]:
	"""Submitted BOQs of an award and/or project that the caller can read."""
	filters = {"docstatus": 1}
	if project:
		filters["project"] = project

	if awarded_quotation:
		rows = frappe.get_list("BOQ", filters={**filters, "awarded_quotation": awarded_quotation}, fields=["name", "project"])
		# A component can name a BOQ the award has not written its link back to yet.
		linked = frappe.get_all(
			"Awarded Quotation Component",
			filters={"parent": awarded_quotation, "parenttype": "Awarded Quotation", "boq": ["is", "set"]},
			pluck="boq",
		)
		if linked:
			rows += frappe.get_list("BOQ", filters={**filters, "name": ["in", linked]}, fields=["name", "project"])
	else:
		rows = frappe.get_list("BOQ", filters=filters, fields=["name", "project"], limit_page_length=0)

	if company:
		projects = {row.project for row in rows if row.project}
		in_company = set(frappe.get_all("Project", filters={"name": ["in", list(projects)], "company": company}, pluck="name"))
		rows = [row for row in rows if row.project in in_company]

	return sorted({row.name for row in rows})


def boq_lines(boqs: list[str]) -> list[dict]:
	"""Every line of `boqs` with its procurement progress, in BOQ order."""
	if not boqs:
		return []

	child = "`tabBOQ Item`"
	rows = frappe.get_list(
		"BOQ",
		# An allowance line has no item to buy; the item lines drawing from it do.
		filters=[["BOQ", "name", "in", boqs], ["BOQ Item", "name", "is", "set"], ["BOQ Item", "is_allowance", "=", 0]],
		fields=[
			"name as boq",
			"project",
			"cost_head",
			"awarded_quotation",
			f"{child}.name as boq_item",
			f"{child}.idx as idx",
			f"{child}.item_code as item_code",
			f"{child}.item_name as item_name",
			f"{child}.wbs as wbs",
			f"{child}.cost_code as cost_code",
			f"{child}.uom as uom",
			f"{child}.boq_qty as boq_qty",
			f"{child}.approved_qty as approved_qty",
			f"{child}.rate as rate",
			f"{child}.approved_rate as approved_rate",
			f"{child}.budget_amount as budget_amount",
		],
		limit_page_length=0,
	)
	rows.sort(key=lambda row: (row.boq, row.idx))

	# Several client BOQ lines can be priced by one internal BOQ (A1 and A2 by the
	# structural one); a line names them all.
	components = {}
	for c in frappe.get_all(
		"Awarded Quotation Component",
		filters={"boq": ["in", boqs], "parenttype": "Awarded Quotation"},
		fields=["boq", "parent", "component"],
		order_by="idx",
	):
		entry = components.setdefault(c.boq, frappe._dict(parent=c.parent, names=[]))
		entry.names.append(c.component)
	items = {
		item.name: item
		for item in frappe.get_all(
			"Item",
			filters={"name": ["in", list({row.item_code for row in rows})]},
			fields=["name", "stock_uom", "item_group", "description"],
		)
	}
	progress = _progress([row.boq_item for row in rows])
	project_names = dict(
		frappe.get_all(
			"Project", filters={"name": ["in", list({row.project for row in rows})]}, fields=["name", "project_name"], as_list=True
		)
	)
	conversions = {}

	lines = []
	for row in rows:
		item = items.get(row.item_code) or frappe._dict()
		uom = row.uom or item.stock_uom
		key = (row.item_code, uom)
		if key not in conversions:
			conversions[key] = _conversion_factor(row.item_code, uom, item.stock_uom)
		factor = conversions[key]
		done = progress.get(row.boq_item) or _empty_progress()
		component = components.get(row.boq)
		approved = flt(row.approved_qty) or flt(row.boq_qty)

		line = {
			"boq": row.boq,
			"boq_item": row.boq_item,
			"project": row.project,
			"project_name": project_names.get(row.project) or row.project,
			"cost_head": row.cost_head,
			"awarded_quotation": row.awarded_quotation or (component.parent if component else None),
			"component": ", ".join(component.names) if component else None,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"item_group": item.item_group,
			"description": item.description,
			"wbs": row.wbs,
			"cost_code": row.cost_code,
			"uom": uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": factor,
			"rate": flt(row.approved_rate) or flt(row.rate),
			"approved_qty": approved,
			"budget_amount": flt(row.budget_amount),
			"requested_qty": flt(done.requested / factor, 3),
			"draft_qty": flt(done.draft / factor, 3),
			"ordered_qty": flt(done.ordered / factor, 3),
			"received_qty": flt(done.received / factor, 3),
			"committed_amount": flt(done.committed, 2),
			"_material_request_items": done.mri,
		}
		line["to_request"] = max(0.0, flt(approved - line["requested_qty"] - line["draft_qty"], 3))
		line["to_order"] = max(0.0, flt(line["requested_qty"] - line["ordered_qty"], 3))
		line["to_receive"] = max(0.0, flt(line["ordered_qty"] - line["received_qty"], 3))
		lines.append(line)
	return lines


def coverage(lines: list[dict]) -> dict:
	"""How much of these lines has been requested, ordered and received, as percentages.

	Each line counts by its budget, so a thousand bricks do not outweigh one
	lift and lines in different units can be added up at all. Lines approved
	without rates count equally.
	"""
	budget = sum(line["budget_amount"] for line in lines)
	weigh = (lambda line: line["budget_amount"]) if budget else (lambda line: 1)
	total = budget or len(lines)

	def share(key):
		if not total:
			return 0
		done = sum(
			weigh(line) * min(1, line[key] / line["approved_qty"]) for line in lines if line["approved_qty"] > 0
		)
		return flt(done / total * 100, 1)

	return {
		"budget": budget,
		"committed": sum(line["committed_amount"] for line in lines),
		"requested": share("requested_qty"),
		"ordered": share("ordered_qty"),
		"received": share("received_qty"),
		"lines": len(lines),
		"lines_received": sum(
			line["approved_qty"] > 0 and line["received_qty"] >= line["approved_qty"] for line in lines
		),
	}


def public(line: dict) -> dict:
	"""A line without the internal keys the server keeps for its own joins."""
	return {key: value for key, value in line.items() if not key.startswith("_")}


def _empty_progress():
	return frappe._dict(requested=0.0, draft=0.0, ordered=0.0, received=0.0, committed=0.0, mri=[])


def _progress(boq_items: list[str]) -> dict:
	"""Stock quantities requested, ordered and received against each BOQ line."""
	progress = {}
	if not boq_items:
		return progress

	mr_item = "`tabMaterial Request Item`"
	by_request_line = {}
	for row in frappe.get_list(
		"Material Request",
		filters=[["Material Request Item", "boq_item", "in", boq_items], ["Material Request", "docstatus", "<", 2]],
		fields=["docstatus", f"{mr_item}.name as mri", f"{mr_item}.boq_item as boq_item", f"{mr_item}.stock_qty as stock_qty"],
		limit_page_length=0,
	):
		done = progress.setdefault(row.boq_item, _empty_progress())
		if row.docstatus == 1:
			done.requested += flt(row.stock_qty)
			done.mri.append(row.mri)
			by_request_line[row.mri] = done
		else:
			done.draft += flt(row.stock_qty)

	if not by_request_line:
		return progress

	po_item = "`tabPurchase Order Item`"
	for row in frappe.get_list(
		"Purchase Order",
		filters=[
			["Purchase Order Item", "material_request_item", "in", list(by_request_line)],
			["Purchase Order", "docstatus", "=", 1],
		],
		fields=[f"{po_item}.material_request_item as mri", f"{po_item}.stock_qty as stock_qty", f"{po_item}.base_net_amount as amount"],
		limit_page_length=0,
	):
		done = by_request_line[row.mri]
		done.ordered += flt(row.stock_qty)
		done.committed += flt(row.amount)

	pr_item = "`tabPurchase Receipt Item`"
	for row in frappe.get_list(
		"Purchase Receipt",
		filters=[
			["Purchase Receipt Item", "material_request_item", "in", list(by_request_line)],
			["Purchase Receipt", "docstatus", "=", 1],
		],
		fields=[f"{pr_item}.material_request_item as mri", f"{pr_item}.stock_qty as stock_qty"],
		limit_page_length=0,
	):
		# Returns carry a negative quantity, so they net off here.
		by_request_line[row.mri].received += flt(row.stock_qty)

	return progress


def _conversion_factor(item_code: str, uom: str | None, stock_uom: str | None) -> float:
	if not uom or not stock_uom or uom == stock_uom:
		return 1.0
	from erpnext.stock.get_item_details import get_conversion_factor

	return flt(get_conversion_factor(item_code, uom).get("conversion_factor")) or 1.0
