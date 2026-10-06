# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Win Loss Analysis - catalogue 2.7.

Submitted quotations (the live issue of each; earlier revisions are cancelled)
and how they ended:

- Won: a sales order was made from it, or an Awarded Quotation names it;
- Lost: declared lost, with its reasons, competitors and the winning price;
- Open: neither yet.

Four views: by sector or by month (count and value won, lost and open, and the
win rate: won ÷ decided), the lost reasons, and the competitor prices against
ours. Values are grand totals in company currency.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import flt, getdate

VIEWS = ("Sector", "Month", "Lost Reasons", "Competitor Prices")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	view = filters.get("view") or "Sector"
	quotes = get_quotations(filters)
	if view == "Lost Reasons":
		return reason_columns(), reason_rows(quotes)
	if view == "Competitor Prices":
		return competitor_columns(), competitor_rows(quotes)
	rows = group_rows(quotes, view)
	return group_columns(view), rows, None, get_chart(rows), get_summary(quotes)


def get_quotations(filters):
	conditions = {"docstatus": 1}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		conditions["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
	quotes = frappe.get_list(
		"Quotation",
		filters=conditions,
		fields=["name", "transaction_date", "status", "base_grand_total", "customer_name", "party_name", "quotation_to",
		        "opportunity", "competitor_price", "grand_total", "order_lost_reason"],
		order_by="transaction_date asc",
		limit_page_length=0,
	)
	if not quotes:
		return []
	names = [q.name for q in quotes]
	awarded = set(frappe.get_all("Awarded Quotation", filters={"quotation": ["in", names], "docstatus": ["<", 2],
	                                                            "status": ["!=", "Cancelled"]}, pluck="quotation"))
	reasons = child_values("Quotation Lost Reason Detail", "lost_reason", names)
	competitors = child_values("Competitor Detail", "competitor", names)
	opp_sector = dict(frappe.get_all("Opportunity", filters={"name": ["in", [q.opportunity for q in quotes if q.opportunity]]},
	                                 fields=["name", "sector"], as_list=True))
	lead_sector = dict(frappe.get_all("Lead", filters={"name": ["in", [q.party_name for q in quotes if q.quotation_to == "Lead"]]},
	                                  fields=["name", "sector"], as_list=True))
	for q in quotes:
		if q.status in ("Ordered", "Partially Ordered") or q.name in awarded:
			q.outcome = "Won"
		elif q.status == "Lost":
			q.outcome = "Lost"
		else:
			q.outcome = "Open"
		q.sector = opp_sector.get(q.opportunity) or lead_sector.get(q.party_name) or _("Not set")
		q.month = getdate(q.transaction_date).strftime("%Y-%m")
		q.reasons = reasons.get(q.name, [])
		q.competitors = competitors.get(q.name, [])
		q.client = q.customer_name or q.party_name
	return quotes


def child_values(doctype, field, parents):
	out = {}
	for parent, value in frappe.get_all(doctype, filters={"parenttype": "Quotation", "parent": ["in", parents]},
	                                    fields=["parent", field], as_list=True, order_by="idx asc"):
		out.setdefault(parent, []).append(value)
	return out


# ---------------------------------------------------------------- by sector / month

def group_columns(view):
	label = _("Sector") if view == "Sector" else _("Month")
	cols = [{"fieldname": "group", "label": label, "fieldtype": "Data", "width": 150}]
	for key, title in (("quoted", _("Quoted")), ("won", _("Won")), ("lost", _("Lost")), ("open", _("Open"))):
		cols.append({"fieldname": f"{key}_count", "label": title, "fieldtype": "Int", "width": 75})
		cols.append({"fieldname": f"{key}_value", "label": _("{0} Value").format(title), "fieldtype": "Currency", "width": 135})
	cols += [
		{"fieldname": "win_rate", "label": _("Win Rate %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "value_win_rate", "label": _("Value Win Rate %"), "fieldtype": "Percent", "width": 130},
	]
	return cols


def group_rows(quotes, view):
	groups = OrderedDict()
	keyed = sorted(quotes, key=lambda q: q.sector if view == "Sector" else q.month)
	for q in keyed:
		key = q.sector if view == "Sector" else q.month
		groups.setdefault(key, []).append(q)
	rows = [tally(month_label(k) if view == "Month" else k, qs) for k, qs in groups.items()]
	if rows:
		total = tally(_("Total"), quotes)
		total["is_total"] = 1
		rows.append(total)
	return rows


def month_label(key):
	return getdate(f"{key}-01").strftime("%b %Y")


def tally(label, quotes):
	row = {"group": label}
	for key, match in (("quoted", None), ("won", "Won"), ("lost", "Lost"), ("open", "Open")):
		subset = [q for q in quotes if match is None or q.outcome == match]
		row[f"{key}_count"] = len(subset)
		row[f"{key}_value"] = sum(flt(q.base_grand_total) for q in subset)
	decided = row["won_count"] + row["lost_count"]
	decided_value = row["won_value"] + row["lost_value"]
	row["win_rate"] = row["won_count"] / decided * 100 if decided else None
	row["value_win_rate"] = row["won_value"] / decided_value * 100 if decided_value else None
	return row


def get_chart(rows):
	rows = [r for r in rows if not r.get("is_total")]
	if not rows:
		return None
	return {
		"data": {
			"labels": [r["group"] for r in rows],
			"datasets": [
				{"name": _("Won"), "values": [r["won_value"] for r in rows]},
				{"name": _("Lost"), "values": [r["lost_value"] for r in rows]},
				{"name": _("Open"), "values": [r["open_value"] for r in rows]},
			],
		},
		"type": "bar",
		"colors": ["#3a8a5c", "#c2452d", "#9aa3ad"],
		"fieldtype": "Currency",
		"barOptions": {"stacked": 1},
	}


def get_summary(quotes):
	won = [q for q in quotes if q.outcome == "Won"]
	lost = [q for q in quotes if q.outcome == "Lost"]
	decided = len(won) + len(lost)
	return [
		{"label": _("Won"), "value": sum(flt(q.base_grand_total) for q in won), "datatype": "Currency", "indicator": "Green"},
		{"label": _("Lost"), "value": sum(flt(q.base_grand_total) for q in lost), "datatype": "Currency", "indicator": "Red"},
		{"label": _("Win Rate (count)"), "value": f"{len(won) / decided * 100:.0f}%" if decided else "—", "datatype": "Data",
		 "indicator": "Blue"},
	]


# ---------------------------------------------------------------- lost reasons

def reason_columns():
	return [
		{"fieldname": "reason", "label": _("Lost Reason"), "fieldtype": "Link", "options": "Quotation Lost Reason", "width": 200},
		{"fieldname": "count", "label": _("Quotations"), "fieldtype": "Int", "width": 100},
		{"fieldname": "share", "label": _("Share of Losses %"), "fieldtype": "Percent", "width": 140},
		{"fieldname": "value", "label": _("Value Lost"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "quotations", "label": _("Quotations"), "fieldtype": "Data", "width": 320},
	]


def reason_rows(quotes):
	lost = [q for q in quotes if q.outcome == "Lost"]
	by_reason = OrderedDict()
	for q in lost:
		for reason in q.reasons or [_("Not given")]:
			by_reason.setdefault(reason, []).append(q)
	rows = [{"reason": reason, "count": len(qs), "share": len(qs) / len(lost) * 100,
	         "value": sum(flt(q.base_grand_total) for q in qs),
	         "quotations": ", ".join(f"{q.name} ({q.client})" for q in qs)} for reason, qs in by_reason.items()]
	return sorted(rows, key=lambda r: (-r["count"], -r["value"]))


# ---------------------------------------------------------------- competitor prices

def competitor_columns():
	return [
		{"fieldname": "quotation", "label": _("Quotation"), "fieldtype": "Link", "options": "Quotation", "width": 160},
		{"fieldname": "client", "label": _("Client"), "fieldtype": "Data", "width": 200},
		{"fieldname": "sector", "label": _("Sector"), "fieldtype": "Data", "width": 110},
		{"fieldname": "transaction_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "our_price", "label": _("Our Price"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "competitors", "label": _("Competitors"), "fieldtype": "Data", "width": 200},
		{"fieldname": "competitor_price", "label": _("Winning Price"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "difference", "label": _("We Were Higher By"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "difference_percent", "label": _("Higher By %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "reasons", "label": _("Lost Reasons"), "fieldtype": "Data", "width": 200},
	]


def competitor_rows(quotes):
	rows = []
	for q in quotes:
		if q.outcome != "Lost" or not (q.competitors or q.competitor_price):
			continue
		price = flt(q.competitor_price)
		rows.append({
			"quotation": q.name, "client": q.client, "sector": q.sector, "transaction_date": q.transaction_date,
			"our_price": q.grand_total, "competitors": ", ".join(q.competitors), "competitor_price": price or None,
			"difference": flt(q.grand_total) - price if price else None,
			"difference_percent": (flt(q.grand_total) - price) / price * 100 if price else None,
			"reasons": ", ".join(q.reasons),
		})
	return rows
