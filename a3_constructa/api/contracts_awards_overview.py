# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "Contracts & Awards Overview" tab of the Contracts & Awards workspace.

Same contract as the other overviews: one call, every figure through
`frappe.get_list` (company-scoped), a section the caller cannot read comes back
`restricted`, money in the company's currency.

The award, milestone, variation and deliverable figures are planning_overview's
own queries, so the two tabs never disagree; this module adds change events, the
monthly flow of change, and the contract-side checks.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, getdate, now_datetime, today

from a3_constructa.a3_constructa.doctype.awarded_quotation.awarded_quotation import ACTIVE_STATUSES
from a3_constructa.a3_constructa.doctype.change_event.change_event import OPEN as CE_OPEN
from a3_constructa.api import planning_overview as po
from a3_constructa.api.utils import default_company, default_currency

DOCTYPES = ("Awarded Quotation", "Variation Order", "Deliverable", "Change Event", "Sales Order", "Project")
CE_SOURCES = ("Client instruction", "Design change", "Site condition", "RFI answer", "Other")
VO_UNANSWERED_DAYS = 30
CE_UNPRICED_DAYS = 14


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	currency = default_currency()
	readable = {d for d in DOCTYPES if po._can_read(d)}
	awards = po._awards(readable, currency, now)
	milestones = po._milestones(readable, now)
	return {
		"generated_at": now_datetime(),
		"currency": currency,
		"awards": awards,
		"milestones": milestones,
		"variations": po._variations(readable, currency),
		"deliverables": po._deliverables(readable, now),
		"change_events": _change_events(readable),
		"trend": _trend(readable, currency, now),
		"health": _health(readable, now, milestones),
	}


def _ce_filters(extra=None):
	filters = {"company": default_company()} if default_company() else {}
	filters.update(extra or {})
	return filters


def _change_events(readable) -> dict:
	if "Change Event" not in readable:
		return {"restricted": True}
	rows = frappe.get_list("Change Event", filters=_ce_filters(), fields=["name", "source", "status", "rough_cost", "rough_days"],
	                       limit_page_length=0)
	open_rows = [r for r in rows if r.status in CE_OPEN]
	by_source = defaultdict(lambda: {"count": 0, "amount": 0.0})
	for r in rows:
		by_source[r.source]["count"] += 1
		by_source[r.source]["amount"] += flt(r.rough_cost)
	return {
		"restricted": False,
		"total": len(rows),
		"open_count": len(open_rows),
		"open_cost": sum(flt(r.rough_cost) for r in open_rows),
		"open_days": sum(r.rough_days or 0 for r in open_rows),
		"unpriced": len([r for r in rows if r.status == "Open"]),
		"open_filters": _ce_filters({"status": ["in", list(CE_OPEN)]}),
		"by_source": [{"label": _(s), "value": s, "count": by_source[s]["count"], "amount": by_source[s]["amount"]}
		              for s in CE_SOURCES if s in by_source],
		"filters": _ce_filters(),
	}


def _trend(readable, currency, now) -> dict:
	"""Per month: rough cost of change raised (change events) against value approved (variation orders)."""
	if "Change Event" not in readable and "Variation Order" not in readable:
		return {"restricted": True}
	start = get_first_day(add_months(now, -11))
	months = []
	for i in range(12):
		first = get_first_day(add_months(start, i))
		months.append({"month": first.strftime("%Y-%m"), "label": first.strftime("%B %Y"), "short": first.strftime("%b"),
		               "raised": 0.0, "approved": 0.0, "raised_count": 0, "approved_count": 0})
	index = {m["month"]: m for m in months}
	if "Change Event" in readable:
		for r in frappe.get_list("Change Event", filters=_ce_filters({"raised_on": [">=", str(start)]}),
		                         fields=["raised_on", "rough_cost", "currency"], limit_page_length=0):
			m = index.get(getdate(r.raised_on).strftime("%Y-%m"))
			if m and (r.currency or currency) == currency:
				m["raised"] += flt(r.rough_cost)
				m["raised_count"] += 1
	if "Variation Order" in readable:
		for r in po._get_list("Variation Order", filters={"status": "Approved", "approved_date": [">=", str(start)]},
		                      fields=["approved_date", "total_amount", "currency"], limit_page_length=0):
			m = index.get(getdate(r.approved_date).strftime("%Y-%m"))
			if m and (r.currency or currency) == currency:
				m["approved"] += flt(r.total_amount)
				m["approved_count"] += 1
	return {"restricted": False, "trend": months}


def _health(readable, now, milestones) -> list[dict]:
	"""Checks that count what needs someone to act, so zero always means healthy."""
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None):
		checks.append({"label": _(label), "severity": severity, "doctype": doctype, "count": count,
		               "filters": filters or {}, "meta": meta})

	award_readable = "Awarded Quotation" in readable
	late_awards = sorted(milestones["overdue_by_award"]) if award_readable else []
	check("Milestones past their planned end", "critical", "Awarded Quotation",
	      milestones.get("overdue_count") if award_readable else None, {"name": ["in", late_awards]},
	      (_("On 1 award") if len(late_awards) == 1 else _("Across {0} awards").format(len(late_awards))) if late_awards else _("See Award Milestones"))

	late_deliverables = {"status": ["in", po.DELIVERABLE_OPEN], "due_date": ["<", str(now)]}
	deliverables = None
	if "Deliverable" in readable:
		deliverables = po._get_list("Deliverable", filters=late_deliverables, pluck="name", limit_page_length=0)
	check("Deliverables past their due date", "critical", "Deliverable",
	      len(deliverables) if deliverables is not None else None, {"name": ["in", deliverables or []]})

	unanswered = None
	if "Variation Order" in readable:
		cutoff = getdate(add_days(now, -VO_UNANSWERED_DAYS))
		unanswered = [r.name for r in po._get_list("Variation Order", filters={"status": "Submitted to Client"},
		                                           fields=["name", "submitted_date", "vo_date"], limit_page_length=0)
		              if getdate(r.submitted_date or r.vo_date) < cutoff]
	check("Variation orders unanswered after 30 days", "warning", "Variation Order",
	      len(unanswered) if unanswered is not None else None, {"name": ["in", unanswered or []]},
	      _("With the client for over a month"))

	unpriced = None
	if "Change Event" in readable:
		unpriced = frappe.get_list("Change Event", filters=_ce_filters({"status": "Open", "raised_on": ["<", str(add_days(now, -CE_UNPRICED_DAYS))]}),
		                           pluck="name", limit_page_length=0)
	check("Change events unpriced after 14 days", "warning", "Change Event",
	      len(unpriced) if unpriced is not None else None, {"name": ["in", unpriced or []]},
	      _("Give them a rough cost so the exposure is known"))

	not_handed = None
	if award_readable:
		awards = po._get_list("Awarded Quotation", filters={"status": ["in", ACTIVE_STATUSES]}, fields=["name", "project"],
		                      limit_page_length=0)
		with_order = set()
		if "Sales Order" in readable and awards:
			with_order = set(frappe.get_list("Sales Order", filters={"awarded_quotation": ["in", [a.name for a in awards]], "docstatus": ["<", 2]},
			                                 pluck="awarded_quotation", limit_page_length=0))
		not_handed = sorted(a.name for a in awards if not a.project or a.name not in with_order)
	check("Awards not handed over to a project", "warning", "Awarded Quotation",
	      len(not_handed) if not_handed is not None else None, {"name": ["in", not_handed or []]},
	      _("No project or no sales order yet: use Hand over to project"))

	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
