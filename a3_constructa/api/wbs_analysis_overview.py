# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "WBS Analysis & Reporting Overview" tab (D-13).

Same contract as the other overviews: one call, the user's default company, a
section the caller may not run comes back `restricted`. Every figure is read
from the P-13 report functions, so the tab and the reports agree:

- Headline: forecast margin at completion across the awards (WIP Schedule:
  revised contract value less forecast cost).
- KPIs: CPI and SPI (Earned Value, company totals); over / under billing (WIP
  Schedule); WBS over budget (the alerts' check, P-13F); checks needing attention.
- Checks: WBS over budget; WBS with CPI or SPI below 0.9; awards under-billed by
  more than 10% of earned; trades below 0.85 productivity in the last 4 weeks;
  alerts sent in the last 7 days. Beside them: the alerts sent.
- Breakdowns: variance by cost head (Job Cost Report); margin by project (Margin
  by WBS); forecast against budget by WBS (Earned Value: EAC against BAC);
  productivity by trade, last 8 weeks (Labour Productivity).
- Trend: the S-curve, cumulative PV, EV and AC by month (Earned Value).
"""

from collections import defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime, today

from a3_constructa.api.utils import default_company, default_currency

INDEX_FLOOR = 0.9
UNDER_BILLED_SHARE = 10  # % of earned
PRODUCTIVITY_FLOOR = 0.85


def _may_run(ref_doctype):
	return frappe.has_permission(ref_doctype, "report") or frappe.has_permission(ref_doctype, "read")


@frappe.whitelist()
def get_overview() -> dict:
	now = getdate(today())
	company = default_company()
	ev = _earned_value(company, now)
	wip = _wip(company, now)
	over = _over_budget()
	labour = _productivity(company, now)
	alerts = _alerts(now)
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"company": company,
		"forecast": _forecast(wip),
		"ev": {k: v for k, v in ev.items() if k != "rows"} if not ev.get("restricted") else ev,
		"billing": _billing(wip),
		"over_budget": over,
		"alerts": alerts,
		"variance": _variance(company, now),
		"margin": _margin(company, now),
		"forecast_by_wbs": _forecast_by_wbs(ev),
		"productivity": labour,
		"health": _health(ev, wip, over, labour, alerts, now),
	}


# ---------------------------------------------------------------- sources

def _earned_value(company, now):
	if not _may_run("WBS"):
		return {"restricted": True}
	from a3_constructa.a3_constructa.report.earned_value import earned_value

	_c, rows, _m, chart, summary = earned_value.execute({"company": company, "as_on": now, "period": "Monthly"})
	total = {s["label"]: s["value"] for s in summary}
	data = chart["data"] if chart else {"labels": [], "datasets": []}
	curve = [{"label": label, "pv": data["datasets"][0]["values"][i], "ev": data["datasets"][1]["values"][i], "ac": data["datasets"][2]["values"][i]}
	         for i, label in enumerate(data["labels"])] if data["datasets"] else []
	return {"restricted": False, "bac": total.get(_("BAC")), "pv": total.get(_("PV")), "ev": total.get(_("EV")), "ac": total.get(_("AC")),
	        "spi": total.get(_("SPI")) if total.get(_("SPI")) != "–" else None,
	        "cpi": total.get(_("CPI")) if total.get(_("CPI")) != "–" else None,
	        "curve": curve, "rows": [r for r in rows if r.get("level") == "WBS"]}


def _wip(company, now):
	if not _may_run("Awarded Quotation"):
		return None
	from a3_constructa.a3_constructa.report.wip_schedule import wip_schedule

	return wip_schedule.execute({"company": company, "as_on": now})[1]


def _forecast(wip):
	if wip is None:
		return {"restricted": True}
	forecast = [r for r in wip if r["forecast_cost"]]
	contract = sum(r["contract_value"] for r in forecast)
	margin = sum(r["forecast_profit"] for r in forecast)
	return {"restricted": False, "margin": margin, "contract": contract, "percent": flt(margin / contract * 100, 1) if contract else None,
	        "without_forecast": len(wip) - len(forecast),
	        "awards": sorted(({"name": r["awarded_quotation"], "label": r["title"], "contract": r["contract_value"], "margin": r["forecast_profit"],
	                           "percent": flt(r["forecast_profit"] / r["contract_value"] * 100, 1) if r["contract_value"] else None}
	                          for r in forecast), key=lambda a: -a["contract"])}


def _billing(wip):
	if wip is None:
		return {"restricted": True}
	over = [r for r in wip if r["over_under"] > 0.005]
	under = [r for r in wip if r["over_under"] < -0.005]
	return {"restricted": False, "over": sum(r["over_under"] for r in over), "under": -sum(r["over_under"] for r in under),
	        "over_count": len(over), "under_count": len(under), "earned": sum(r["earned"] for r in wip), "billed": sum(r["billed"] for r in wip),
	        "under_awards": [r["awarded_quotation"] for r in under if r["earned"] and -r["over_under"] > r["earned"] * UNDER_BILLED_SHARE / 100]}


def _over_budget():
	if not _may_run("WBS"):
		return {"restricted": True}
	from a3_constructa.api.alerts import wbs_over_budget

	items = wbs_over_budget()
	return {"restricted": False, "count": len(items), "names": [i["name"] for i in items],
	        "rows": [{"name": i["name"], "percent": flt(i["value"], 1), "detail": i["detail"]} for i in items]}


def _productivity(company, now):
	if not _may_run("Timesheet"):
		return {"restricted": True}
	from a3_constructa.api.labour import productivity

	rows = productivity(company, None, add_days(now, -56), now)
	by_trade = defaultdict(lambda: {"planned": 0.0, "hours": 0.0, "low_weeks": 0, "weeks": 0})
	recent = add_days(now, -28)
	low_recent = set()
	for r in rows:
		if r["factor"] is None:
			continue
		t = by_trade[r["trade"]]
		t["planned"] += r["planned_hours"]
		t["hours"] += r["hours"]
		t["weeks"] += 1
		if r["flag"]:
			t["low_weeks"] += 1
			if getdate(r["week"]) >= getdate(recent) - timedelta(days=6):  # a week that overlaps the last 28 days
				low_recent.add(r["trade"])
	trades = [{"label": _(trade), "value": trade, "factor": flt(t["planned"] / t["hours"], 2) if t["hours"] else None,
	           "hours": flt(t["hours"], 1), "planned": flt(t["planned"], 1), "low_weeks": t["low_weeks"], "weeks": t["weeks"]}
	          for trade, t in by_trade.items()]
	return {"restricted": False, "from": add_days(now, -56), "recent_from": recent, "trades": sorted(trades, key=lambda t: t["factor"] or 0),
	        "low_recent": sorted(low_recent)}


def _alerts(now):
	if not frappe.has_permission("Alert Rule", "read"):
		return {"restricted": True}
	since = add_days(now_datetime(), -7)
	rules = {r.name: r.rule_name for r in frappe.get_list("Alert Rule", fields=["name", "rule_name"], limit_page_length=0)}
	logs = frappe.get_all("Alert Log", filters={"parenttype": "Alert Rule", "parent": ["in", list(rules) or [""]], "sent_on": [">=", since]},
	                      fields=["parent", "reference_doctype", "reference_name", "detail", "sent_on"], order_by="sent_on desc")
	return {"restricted": False, "count": len(logs), "rules": sorted({l.parent for l in logs}),
	        "list": [{"rule": rules.get(l.parent, l.parent), "rule_name": l.parent, "doctype": l.reference_doctype, "name": l.reference_name,
	                  "detail": l.detail, "sent_on": l.sent_on} for l in logs[:8]]}


def _variance(company, now):
	if not _may_run("WBS"):
		return {"restricted": True}
	from a3_constructa.a3_constructa.report.job_cost_report import job_cost_report

	rows = job_cost_report.execute({"company": company, "as_on": now, "depth": "Cost Head", "hide_zero": 1})[1]
	heads = defaultdict(lambda: {"revised": 0.0, "forecast": 0.0, "variance": 0.0})
	for r in rows:
		if r.get("level") != "Cost Head":
			continue
		h = heads[r["label"]]
		h["revised"] += flt(r.get("revised_budget"))
		h["forecast"] += flt(r.get("forecast"))
		h["variance"] += flt(r.get("variance"))
	return {"restricted": False, "rows": sorted(({"label": k, **v} for k, v in heads.items()), key=lambda r: r["variance"])}


def _margin(company, now):
	if not _may_run("WBS"):
		return {"restricted": True}
	from a3_constructa.a3_constructa.report.margin_by_wbs import margin_by_wbs

	rows = [r for r in margin_by_wbs.execute({"company": company, "as_on": now, "hide_zero": 1})[1] if r["level"] == "Project"]
	return {"restricted": False, "rows": [{"label": r["label"], "project": r["project"], "revenue": r["revenue"], "cost": r["cost"],
	                                         "margin": r["margin"], "percent": flt(r["margin_percent"], 1) if r["margin_percent"] is not None else None}
	                                        for r in sorted(rows, key=lambda r: -r["revenue"])]}


def _forecast_by_wbs(ev):
	if ev.get("restricted"):
		return {"restricted": True}
	leaves = [r for r in ev["rows"] if flt(r.get("bac")) > 0 and not any(o["parent_key"] == r["key"] and flt(o.get("bac")) > 0 for o in ev["rows"])]
	rows = [{"label": r["label"], "wbs": r["wbs"], "project": r["project"], "bac": r["bac"],
	         "eac": r["eac"] if r["eac"] is not None else None, "ac": r["ac"], "cpi": r["cpi"]} for r in leaves]
	return {"restricted": False, "rows": sorted(rows, key=lambda r: -r["bac"])[:8]}


def _health(ev, wip, over, labour, alerts, now):
	checks = []

	def check(label, severity, doctype, count, filters=None, meta=None, report=None):
		checks.append({"label": _(label), "severity": severity, "doctype": doctype, "count": count, "filters": filters or {}, "meta": meta,
		               "report": report})

	check("WBS over budget", "critical", "WBS", None if over.get("restricted") else over["count"],
	      {"name": ["in", over.get("names") or []]}, _("Committed and spent past the budget the buying check uses"))
	low = None
	if not ev.get("restricted"):
		# Only nodes with a budget: without one there is nothing to earn, so the indices mean nothing.
		low = sorted({r["wbs"] for r in ev["rows"] if flt(r.get("bac")) > 0 and ((r["cpi"] is not None and r["cpi"] < INDEX_FLOOR)
		                                                                       or (r["spi"] is not None and r["spi"] < INDEX_FLOOR))})
	check("WBS with CPI or SPI below 0.9", "warning", "WBS", None if low is None else len(low), {"name": ["in", low or []]},
	      _("Over cost or behind the baseline (Earned Value)"))
	under = None if wip is None else _billing(wip)["under_awards"]
	check("Awards under-billed by over 10% of earned", "warning", "Awarded Quotation", None if under is None else len(under),
	      {"name": ["in", under or []]}, _("Work done and not yet billed (WIP Schedule)"))
	trades = None if labour.get("restricted") else labour["low_recent"]
	check("Trades below 0.85 productivity, last 4 weeks", "warning", "Timesheet", None if trades is None else len(trades),
	      {"company": default_company(), "from_date": str(labour.get("recent_from") or ""), "to_date": str(now)},
	      ", ".join(_(t) for t in trades) if trades else _("Planned ÷ actual hours (Labour Productivity)"), report="Labour Productivity")
	check("Alerts sent in the last 7 days", "warning", "Alert Rule", None if alerts.get("restricted") else alerts["count"],
	      {"name": ["in", alerts.get("rules") or []]}, _("From the alert rules (P-13F)"))
	return sorted(checks, key=lambda c: (c["count"] is None, not c["count"], c["severity"] != "critical"))
