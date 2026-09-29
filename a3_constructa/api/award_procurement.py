# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Procurement for each awarded project, from its approved BOQ to what has arrived.

`award_rows()` gives one row per award, for the Procurement overview and for the
Award Procurement page before an award is chosen. `get_award_procurement()` is
everything that page shows for one award.

An award's buying is read two ways. Traced: its approved BOQ lines followed
through request, order and receipt (a3_constructa.api.boq_procurement).
Project: every buying document for the award's project, which also catches
what was bought outside the BOQ.
"""

from collections import defaultdict

import frappe
from frappe.utils import date_diff, flt, getdate, now_datetime, today

from a3_constructa.a3_constructa.doctype.awarded_quotation.awarded_quotation import ACTIVE_STATUSES
from a3_constructa.api.boq_procurement import boq_lines, can_trace, coverage, public
from a3_constructa.api.utils import default_company, default_currency

AWARD_FIELDS = ["name", "title", "customer", "status", "project", "currency", "revised_contract_value"]
OPEN_PO_STATUSES = ("To Receive and Bill", "To Receive")
SHIPMENT_DONE = ("Received at Warehouse", "Received at Site", "Closed")
PENDING_LINES = 10
RECENT_DOCUMENTS = 6


def award_boqs(awards: list[str]) -> dict[str, str]:
	"""Approved BOQ -> the award it prices, for the awards given."""
	if not awards:
		return {}
	mapping = {
		row.name: row.awarded_quotation
		for row in frappe.get_list(
			"BOQ",
			filters={"docstatus": 1, "awarded_quotation": ["in", awards]},
			fields=["name", "awarded_quotation"],
			limit_page_length=0,
		)
	}
	# A component can name a BOQ the award has not written its link back to yet.
	named = {
		c.boq: c.parent
		for c in frappe.get_all(
			"Awarded Quotation Component",
			filters={"parent": ["in", awards], "parenttype": "Awarded Quotation", "boq": ["is", "set"]},
			fields=["parent", "boq"],
		)
		if c.boq not in mapping
	}
	if named:
		approved = set(frappe.get_list("BOQ", filters={"docstatus": 1, "name": ["in", list(named)]}, pluck="name"))
		mapping.update({boq: award for boq, award in named.items() if boq in approved})
	return mapping


def award_rows(awards: list) -> tuple[list[dict], list[dict]]:
	"""One row per award with its BOQ coverage, and every traced line behind them."""
	mapping = award_boqs([award.name for award in awards])
	lines = boq_lines(sorted(mapping))
	by_award = defaultdict(list)
	for line in lines:
		by_award[mapping[line["boq"]]].append(line)

	rows = []
	for award in awards:
		own = by_award.get(award.name, [])
		rows.append(
			{
				"name": award.name,
				"title": award.title,
				"customer": award.customer,
				"status": award.status,
				"project": award.project,
				"currency": award.currency,
				"boqs": len({line["boq"] for line in own}),
				**coverage(own),
			}
		)
	return rows, lines


def active_awards() -> list:
	"""The default company's live awards."""
	filters = {"status": ["in", ACTIVE_STATUSES]}
	if default_company():
		filters["company"] = default_company()
	return frappe.get_list(
		"Awarded Quotation",
		filters=filters,
		fields=AWARD_FIELDS,
		order_by="revised_contract_value desc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_award_procurement(awarded_quotation: str | None = None) -> dict:
	result = {"generated_at": now_datetime(), "currency": default_currency(), "restricted": not can_trace()}
	if result["restricted"]:
		return result

	if not awarded_quotation:
		result["award"] = None
		result["awards"] = award_rows(active_awards())[0] if frappe.has_permission("Awarded Quotation", "read") else []
		return result

	award = frappe.get_doc("Awarded Quotation", awarded_quotation)
	award.check_permission("read")
	rows, lines = award_rows([frappe._dict({field: award.get(field) for field in AWARD_FIELDS})])

	result["currency"] = award.currency or result["currency"]
	result["award"] = {
		**rows[0],
		"value": flt(award.revised_contract_value),
		"progress": flt(award.progress_percent),
		"start": award.start_date,
		"end": award.revised_end_date or award.end_date,
		"project_name": frappe.db.get_value("Project", award.project, "project_name") if award.project else None,
	}
	result["components"] = _components(lines)
	result["pending"] = _pending(lines)
	result.update(_documents(award, lines))
	return result


def _components(lines: list[dict]) -> list[dict]:
	"""Coverage per package: each BOQ under its cost head, with the client lines it prices."""
	groups = defaultdict(list)
	for line in lines:
		groups[line["boq"]].append(line)
	heads = dict(
		frappe.get_all(
			"Cost Head",
			filters={"name": ["in", list({l["cost_head"] for l in lines if l["cost_head"]}) or [""]]},
			fields=["name", "cost_head_name"],
			as_list=True,
		)
	)
	rows = []
	for boq, group in groups.items():
		head = group[0]["cost_head"]
		rows.append({"label": heads.get(head) or head or boq, "boq": boq, "components": group[0]["component"],
		             **coverage(group)})
	return sorted(rows, key=lambda row: -row["budget"])


def _pending(lines: list[dict]) -> list[dict]:
	"""The lines with the most budget still to buy."""

	def open_value(line):
		done = min(1, line["received_qty"] / line["approved_qty"]) if line["approved_qty"] else 1
		return line["budget_amount"] * (1 - done)

	open_lines = [line for line in lines if line["to_request"] or line["to_order"] or line["to_receive"]]
	open_lines.sort(key=open_value, reverse=True)
	return [public(line) for line in open_lines[:PENDING_LINES]]


def _documents(award, lines: list[dict]) -> dict:
	"""The award's requests, orders, receipts and shipments, traced and by project."""
	now = getdate(today())
	project = award.project
	boqs = sorted({line["boq"] for line in lines})
	traced_request_lines = sorted({mri for line in lines for mri in line["_material_request_items"]})

	def names(doctype, child, field, values):
		if not values:
			return set()
		return set(
			frappe.get_list(
				doctype,
				filters=[[child, field, "in" if isinstance(values, list) else "=", values], [doctype, "docstatus", "<", 2]],
				pluck="name",
				distinct=True,
				limit_page_length=0,
			)
		)

	requests = names("Material Request", "Material Request Item", "boq", boqs)
	orders = names("Purchase Order", "Purchase Order Item", "material_request_item", traced_request_lines)
	if project:
		requests |= names("Material Request", "Material Request Item", "project", project)
		orders |= names("Purchase Order", "Purchase Order Item", "project", project)
	receipts = names("Purchase Receipt", "Purchase Receipt Item", "purchase_order", sorted(orders))
	if project:
		receipts |= names("Purchase Receipt", "Purchase Receipt Item", "project", project)

	def recent(doctype, pool, fields, date_field):
		if not pool:
			return []
		return frappe.get_list(
			doctype,
			filters={"name": ["in", sorted(pool)]},
			fields=fields,
			order_by=f"{date_field} desc",
			limit_page_length=RECENT_DOCUMENTS,
		)

	def by_status(doctype, pool):
		if not pool:
			return []
		rows = frappe.get_list(
			doctype, filters={"name": ["in", sorted(pool)]}, fields=["status", "count(name) as n"], group_by="status"
		)
		return [{"label": row.status, "value": row.status, "count": row.n} for row in sorted(rows, key=lambda r: -r.n)]

	late = []
	if orders:
		for po in frappe.get_list(
			"Purchase Order",
			filters={
				"name": ["in", sorted(orders)],
				"docstatus": 1,
				"status": ["in", OPEN_PO_STATUSES],
				"schedule_date": ["<", now],
			},
			fields=["name", "supplier", "schedule_date", "per_received", "base_net_total"],
			order_by="schedule_date asc",
			limit_page_length=0,
		):
			late.append({**po, "days_late": date_diff(now, po.schedule_date)})

	shipments = []
	if frappe.has_permission("Shipment Tracking", "read") and (orders or project):
		found = {}
		for filters in (
			[["Shipment Tracking", "purchase_order", "in", sorted(orders)]] if orders else None,
			[["Shipment Tracking", "project", "=", project]] if project else None,
		):
			if not filters:
				continue
			for row in frappe.get_list(
				"Shipment Tracking",
				filters=filters + [["Shipment Tracking", "docstatus", "<", 2], ["Shipment Tracking", "status", "not in", SHIPMENT_DONE]],
				fields=["name", "supplier", "status", "purchase_order", "expected_receipt_date", "shipment_type"],
				limit_page_length=0,
			):
				found[row.name] = row
		shipments = sorted(found.values(), key=lambda s: str(s.expected_receipt_date or "9999"))

	# Money committed for the project on order lines no BOQ line leads to.
	off_boq = {"amount": 0.0, "orders": 0}
	if project:
		traced = set(traced_request_lines)
		off_orders = set()
		for row in frappe.get_list(
			"Purchase Order",
			filters=[["Purchase Order", "docstatus", "=", 1], ["Purchase Order Item", "project", "=", project]],
			fields=["name", "`tabPurchase Order Item`.material_request_item as mri", "`tabPurchase Order Item`.base_net_amount as amount"],
			limit_page_length=0,
		):
			if row.mri not in traced:
				off_boq["amount"] += flt(row.amount)
				off_orders.add(row.name)
		off_boq["orders"] = len(off_orders)
		off_boq["order_names"] = sorted(off_orders)

	return {
		"requests": recent(
			"Material Request", requests, ["name", "transaction_date", "schedule_date", "status", "per_ordered"], "transaction_date"
		),
		"orders": recent(
			"Purchase Order",
			orders,
			["name", "supplier", "transaction_date", "schedule_date", "status", "base_net_total", "per_received"],
			"transaction_date",
		),
		"receipts": recent(
			"Purchase Receipt", receipts, ["name", "supplier", "posting_date", "status", "base_net_total"], "posting_date"
		),
		"request_statuses": by_status("Material Request", requests),
		"order_statuses": by_status("Purchase Order", orders),
		"document_counts": {"requests": len(requests), "orders": len(orders), "receipts": len(receipts)},
		"late_orders": late,
		"shipments": shipments,
		"off_boq": off_boq,
	}
