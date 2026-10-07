# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Data for the "A3 Constructa Overview" tab of the home workspace (D-15).

One call that asks every module overview for its data, as the user, and keeps
two things from each: its headline (the figure its own tab leads with, worked
out exactly as that tab does) and its "Needs attention" checks. A module the
user cannot open, or one that fails, is marked so and the rest still load.

- Headline: the order book (revised contract value of the active awards,
  Contracts & Awards) and the active projects.
- KPIs: active projects; critical checks across the modules; alerts sent in
  the last 7 days; checks needing attention.
- One card per module, in the home's division order, with its headline and
  how many of its checks fail, opening its workspace.
- Needs attention: every failing check of every module, critical first, then
  warnings, each naming its module.
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from a3_constructa.api.utils import default_company, default_currency

# (division, workspace, overview module)
MODULES = [
	("Core", "WBS & Cost Structure", "wbs_cost_structure"),
	("Win", "CRM & Estimating", "crm_estimating"),
	("Win", "Contracts & Awards", "contracts_awards"),
	("Win", "Sales & Billing", "sales_billing"),
	("Plan", "Planning & Budgeting", "planning"),
	("Plan", "Project Operations", "project_operations"),
	("Resource", "HR & Time", "hr_time"),
	("Resource", "Asset & Equipment", "asset_equipment"),
	("Buy", "Procurement", "procurement"),
	("Buy", "Delivery & Logistics", "delivery_logistics"),
	("Buy", "Inventory Movement", "inventory_movement"),
	("Control", "Finance & Accounting", "finance_accounting"),
	("Control", "WBS Analysis & Reporting", "wbs_analysis"),
	("Control", "Master Data", "master_data"),
]


@frappe.whitelist()
def get_overview() -> dict:
	modules, checks, data = [], [], {}
	for division, workspace, module in MODULES:
		entry = {"division": _(division), "workspace": workspace, "label": _(workspace),
		         "route": "/app/" + quote(workspace.lower().replace(" ", "-"), safe="-")}
		if not frappe.has_permission("Workspace", "read", workspace) and not frappe.db.get_value("Workspace", workspace, "public"):
			modules.append({**entry, "restricted": True})
			continue
		try:
			o = frappe.get_attr(f"a3_constructa.api.{module}_overview.get_overview")()
		except frappe.PermissionError:
			modules.append({**entry, "restricted": True})
			continue
		except Exception:
			frappe.log_error(title=f"Home overview: {workspace}")
			modules.append({**entry, "failed": True})
			continue
		data[module] = o
		failing = [c for c in o.get("health") or [] if c.get("count")]
		for c in failing:
			checks.append({**c, "module": _(workspace), "meta": f"{_(workspace)} · {c.get('meta') or _(c.get('doctype') or '')}"})
		modules.append({**entry, "restricted": False, "headline": headline(module, o),
		                "critical": sum(1 for c in failing if c["severity"] == "critical"),
		                "warning": sum(1 for c in failing if c["severity"] != "critical"),
		                "checks": sum(1 for c in o.get("health") or [] if c.get("count") is not None)})
	checks.sort(key=lambda c: (c["severity"] != "critical", -flt(c["count"])))
	return {
		"generated_at": now_datetime(),
		"currency": default_currency(),
		"company": default_company(),
		"book": _book(data),
		"projects": _projects(data),
		"alerts": _alerts(data),
		"modules": modules,
		"health": checks,
		"measured": sum(m.get("checks") or 0 for m in modules),
	}


# ---------------------------------------------------------------- headlines

def headline(module, o) -> dict:
	"""The figure each module's own tab leads with, worked out as that tab does.
	kind: money, count, percent; restricted when the tab would say so."""
	h = HEADLINES[module](o)
	return {"restricted": True, "label": h[0]} if h[1] is None else {"restricted": False, "label": h[0], "value": h[1], "kind": h[2], "note": h[3]}


def _r(section):
	return not section or section.get("restricted")


def _wbs_cost(o):
	a = o.get("allocation") or {}
	if _r(a):
		return _("Approved budget on the works"), None, None, None
	return _("Approved budget on the works"), flt(a.get("percent")), "percent", _("of the approved BOQ allocated to WBS")


def _crm(o):
	p = o.get("pipeline") or {}
	return (_("Weighted pipeline"), None, None, None) if _r(p) else (_("Weighted pipeline"), flt(p.get("weighted")), "money",
	                                                                  _("{0} open opportunities").format(p.get("count")))


def _awards(o, label):
	a = o.get("awards") or {}
	return (label, None, None, None) if _r(a) else (label, flt(a.get("order_book")), "money",
	                                                 _("{0} active awards").format(a.get("active_count")))


def _sales(o):
	r, i = o.get("receivable") or {}, o.get("ipcs") or {}
	if _r(r):
		return _("Certified but not invoiced, plus receivable"), None, None, None
	unbilled = 0 if _r(i) else flt(i.get("certified_unbilled"))
	return _("Certified but not invoiced, plus receivable"), flt(r.get("total")) + unbilled, "money", _("owed by the clients")


def _operations(o):
	p = o.get("progress") or {}
	return (_("Complete, against planned"), None, None, None) if _r(p) else (
		_("Complete, against planned"), flt(p.get("percent")), "percent", _("{0}% planned").format(p.get("planned")))


def _hr(o):
	w = o.get("workforce") or {}
	return (_("Workforce"), None, None, None) if _r(w) else (_("Workforce"), w.get("active"), "count", _("active employees"))


def _assets(o):
	r = o.get("register") or {}
	return (_("Asset register"), None, None, None) if _r(r) else (_("Asset register"), r.get("count"), "count", _("assets"))


def _procurement(o):
	po = o.get("orders") or {}
	return (_("Still to arrive"), None, None, None) if _r(po) else (_("Still to arrive"), flt(po.get("open_value")), "money",
	                                                                _("on {0} open purchase orders").format(po.get("open_count")))


def _delivery(o):
	s = o.get("shipments") or {}
	return (_("On the way"), None, None, None) if _r(s) else (_("On the way"), s.get("active"), "count",
	                                                          _("shipments, {0} late").format(s.get("late_count")))


def _inventory(o):
	s = o.get("stock") or {}
	return (_("Stock on hand"), None, None, None) if _r(s) else (_("Stock on hand"), flt(s.get("value")), "money", _("in the company's stores"))


def _finance(o):
	c = o.get("cash") or {}
	return (_("Cash & bank"), None, None, None) if _r(c) else (_("Cash & bank"), flt(c.get("total")), "money", _("in bank and cash accounts"))


def _analysis(o):
	f = o.get("forecast") or {}
	return (_("Forecast margin at completion"), None, None, None) if _r(f) else (
		_("Forecast margin at completion"), flt(f.get("margin")), "money",
		_("{0}% of contract value").format(f.get("percent")) if f.get("percent") is not None else "")


def _master(o):
	areas = o.get("areas") or []
	ready = [a for a in areas if (a.get("count") or 0) > 0]
	return _("Setup coverage"), len(ready), "count", _("of {0} master areas have records").format(len(areas))


HEADLINES = {
	"wbs_cost_structure": _wbs_cost, "crm_estimating": _crm, "contracts_awards": lambda o: _awards(o, _("Revised contract value")),
	"sales_billing": _sales, "planning": lambda o: _awards(o, _("Order book")), "project_operations": _operations, "hr_time": _hr,
	"asset_equipment": _assets, "procurement": _procurement, "delivery_logistics": _delivery, "inventory_movement": _inventory,
	"finance_accounting": _finance, "wbs_analysis": _analysis, "master_data": _master,
}


# ---------------------------------------------------------------- summary

def _book(data):
	a = (data.get("contracts_awards") or {}).get("awards") or {}
	if _r(a):
		return {"restricted": True}
	wip = (data.get("wbs_analysis") or {}).get("billing") or {}
	return {"restricted": False, "value": flt(a.get("order_book")), "active": a.get("active_count"),
	        "earned": None if _r(wip) else flt(wip.get("earned")), "billed": None if _r(wip) else flt(wip.get("billed"))}


def _projects(data):
	p = (data.get("project_operations") or {}).get("progress") or {}
	if _r(p):
		return {"restricted": True}
	return {"restricted": False, "count": len(p.get("projects") or []), "percent": p.get("percent"), "planned": p.get("planned"),
	        "rows": p.get("projects") or []}


def _alerts(data):
	a = (data.get("wbs_analysis") or {}).get("alerts") or {}
	return {"restricted": True} if _r(a) else {"restricted": False, "count": a.get("count")}
