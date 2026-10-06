# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Equipment Utilisation - build sheet head 57, row 39; catalogue 8.3.

Per machine and site, from the submitted Equipment Logs in the period: the days
logged, hours worked, idle and broken down, and

- available hours = worked + idle (on site and able to work);
- utilisation = worked ÷ available: how much of the time it could work, it did;
- availability = available ÷ (available + breakdown): how much of the time it was
  not broken down;
- cost and cost per worked hour: owned plant at its internal rate (what the logs
  charged the job); hired plant at what the supplier invoiced against its hire
  order in the period.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.from_date = getdate(filters.get("from_date") or add_months(nowdate(), -1))
	filters.to_date = getdate(filters.get("to_date") or nowdate())
	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	cur = {"fieldtype": "Currency", "options": "currency"}
	hours = {"fieldtype": "Float", "precision": 1}
	return [
		{"fieldname": "asset", "label": _("Machine"), "fieldtype": "Link", "options": "Asset", "width": 110},
		{"fieldname": "asset_name", "label": _("Name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "ownership", "label": _("Owned / Hired"), "fieldtype": "Data", "width": 105},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location", "width": 140},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "days", "label": _("Days Logged"), "fieldtype": "Int", "width": 95},
		{"fieldname": "worked", "label": _("Worked h"), **hours, "width": 90},
		{"fieldname": "idle", "label": _("Idle h"), **hours, "width": 80},
		{"fieldname": "breakdown", "label": _("Breakdown h"), **hours, "width": 100},
		{"fieldname": "available", "label": _("Available h"), **hours, "width": 95},
		{"fieldname": "utilisation", "label": _("Utilisation %"), "fieldtype": "Percent", "width": 105},
		{"fieldname": "availability", "label": _("Availability %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "cost", "label": _("Cost"), **cur, "width": 110},
		{"fieldname": "cost_per_hour", "label": _("Cost per Worked h"), **cur, "width": 125},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_data(filters):
	conditions = {"docstatus": 1, "log_date": ["between", [filters.from_date, filters.to_date]]}
	for f in ("asset", "project", "site", "company"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	if filters.get("asset_category"):
		conditions["asset"] = ["in", frappe.get_all("Asset", filters={"asset_category": filters.asset_category}, pluck="name") or [""]]
	logs = frappe.get_list("Equipment Log", filters=conditions,
	                       fields=["asset", "asset_name", "site", "project", "log_date", "worked_hours", "idle_hours", "breakdown_hours",
	                               "amount", "is_hired", "company"], limit_page_length=0)
	groups = {}
	for log in logs:
		g = groups.setdefault((log.asset, log.site, log.project), {
			"asset": log.asset, "asset_name": log.asset_name, "site": log.site, "project": log.project, "is_hired": log.is_hired,
			"dates": set(), "worked": 0.0, "idle": 0.0, "breakdown": 0.0, "cost": 0.0,
			"currency": frappe.get_cached_value("Company", log.company, "default_currency")})
		g["dates"].add(log.log_date)
		g["worked"] += flt(log.worked_hours)
		g["idle"] += flt(log.idle_hours)
		g["breakdown"] += flt(log.breakdown_hours)
		g["cost"] += flt(log.amount)
	hire_cost = hired_costs(filters, {g["asset"] for g in groups.values() if g["is_hired"]})
	# A hire invoice is for the machine, not a site: split it over the sites by hours worked.
	hired_hours = {}
	for g in groups.values():
		if g["is_hired"]:
			hired_hours[g["asset"]] = hired_hours.get(g["asset"], 0) + g["worked"]
	data = []
	for g in groups.values():
		if g["is_hired"]:
			total = hired_hours.get(g["asset"]) or 0
			g["cost"] = hire_cost.get(g["asset"], 0) * (g["worked"] / total if total else 0)
		available = g["worked"] + g["idle"]
		data.append({
			**{k: g[k] for k in ("asset", "asset_name", "site", "project", "worked", "idle", "breakdown", "currency")},
			"ownership": _("Hired") if g["is_hired"] else _("Owned"),
			"days": len(g["dates"]),
			"available": available,
			"utilisation": g["worked"] / available * 100 if available else 0,
			"availability": available / (available + g["breakdown"]) * 100 if available + g["breakdown"] else 0,
			"cost": flt(g["cost"], 2),
			"cost_per_hour": flt(g["cost"] / g["worked"], 2) if g["worked"] else 0,
		})
	data.sort(key=lambda r: (r["asset_name"] or "", r["site"] or ""))
	return data


def hired_costs(filters, assets):
	"""What suppliers invoiced, in the period, against each hired machine's hire order."""
	out = {}
	for asset in assets:
		po = frappe.db.get_value("Asset", asset, "hire_purchase_order")
		if not po:
			continue
		out[asset] = flt(frappe.db.sql("""select sum(item.base_net_amount) from `tabPurchase Invoice Item` item
			join `tabPurchase Invoice` pi on pi.name = item.parent
			where item.purchase_order = %s and pi.docstatus = 1 and pi.posting_date between %s and %s""",
			(po, filters.from_date, filters.to_date))[0][0])
	return out


def get_summary(data):
	if not data:
		return []
	worked = sum(r["worked"] for r in data)
	available = sum(r["available"] for r in data)
	breakdown = sum(r["breakdown"] for r in data)
	cost = sum(r["cost"] for r in data)
	return [
		{"label": _("Worked hours"), "value": worked, "datatype": "Float", "indicator": "Blue"},
		{"label": _("Utilisation"), "value": f"{worked / available * 100:.0f}%" if available else "—", "datatype": "Data"},
		{"label": _("Breakdown hours"), "value": breakdown, "datatype": "Float", "indicator": "Red" if breakdown else "Green"},
		{"label": _("Plant cost"), "value": cost, "datatype": "Currency", "currency": data[0]["currency"]},
	]
