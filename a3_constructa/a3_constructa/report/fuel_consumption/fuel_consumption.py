# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Fuel Consumption - catalogue 8.4: litres per worked hour, machine by machine.

For the period: the fuel issued to each machine (material issues naming it), its
cost, the hours it worked (submitted Equipment Logs), litres per hour, and that
against the machine's norm (Asset.fuel_norm_lph): more than 15% over is flagged.
Fuel with no hours logged is flagged too. Filters: company, from / to, project,
machine.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from a3_constructa.overrides.fuel import ISSUES, fuel_groups

TOLERANCE = 15


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = data(filters)
	return columns(), rows, None, None, summary(rows)


def data(filters):
	start = getdate(filters.get("from_date") or add_days(today(), -30))
	end = getdate(filters.get("to_date") or today())
	groups = fuel_groups()
	values = {"start": start, "end": end, "groups": groups or [""], "issues": ISSUES}
	cond_fuel, cond_log = [], []
	for key, field_fuel, field_log in (("project", "d.project", "l.project"), ("asset", "d.asset", "l.asset"),
	                                   ("company", "se.company", "l.company")):
		if filters.get(key):
			values[key] = filters[key]
			cond_fuel.append(f"{field_fuel} = %({key})s"); cond_log.append(f"{field_log} = %({key})s")
	fuel = frappe.db.sql(f"""select d.asset, sum(d.transfer_qty) litres, sum(d.amount) cost, count(distinct se.name) issues
		from `tabStock Entry Detail` d join `tabStock Entry` se on se.name = d.parent join `tabItem` i on i.name = d.item_code
		where se.docstatus = 1 and se.purpose in %(issues)s and d.asset is not null and i.item_group in %(groups)s
			and se.posting_date between %(start)s and %(end)s {''.join(' and ' + c for c in cond_fuel)}
		group by d.asset""", values, as_dict=True)
	hours = frappe.db.sql(f"""select l.asset, sum(l.worked_hours) worked from `tabEquipment Log` l
		where l.docstatus = 1 and l.log_date between %(start)s and %(end)s {''.join(' and ' + c for c in cond_log)}
		group by l.asset""", values, as_dict=True)
	by_asset = {}
	for r in fuel:
		by_asset.setdefault(r.asset, {}).update(litres=flt(r.litres), cost=flt(r.cost), issues=r.issues)
	for r in hours:
		by_asset.setdefault(r.asset, {}).update(worked=flt(r.worked))
	rows = []
	for asset, v in by_asset.items():
		a = frappe.db.get_value("Asset", asset, ["asset_name", "asset_category", "project", "fuel_norm_lph", "is_hired"], as_dict=True)
		litres, worked, norm = v.get("litres", 0), v.get("worked", 0), flt(a.fuel_norm_lph)
		lph = flt(litres / worked, 2) if worked and litres else None
		variance = flt((lph - norm) / norm * 100, 1) if lph is not None and norm else None
		if not litres:
			flag = ""  # no fuel issued: a hired machine fuelled by its hirer, or not yet issued
		elif not worked:
			flag = _("Fuel with no hours logged")
		elif variance is not None and variance > TOLERANCE:
			flag = _("{0}% over the norm").format(variance)
		elif litres and not norm:
			flag = _("No norm set")
		else:
			flag = ""
		rows.append({"asset": asset, "asset_name": a.asset_name, "category": a.asset_category, "project": a.project,
		             "litres": flt(litres, 1), "cost": flt(v.get("cost"), 2), "issues": v.get("issues", 0), "worked_hours": flt(worked, 1),
		             "lph": lph, "norm": norm or None, "variance": variance, "flag": flag, "is_hired": a.is_hired})
	return sorted(rows, key=lambda r: (not r["flag"], -(r["variance"] or 0), r["asset_name"] or ""))


def columns():
	return [
		{"fieldname": "asset", "label": _("Machine"), "fieldtype": "Link", "options": "Asset", "width": 140},
		{"fieldname": "asset_name", "label": _("Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 130},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 100},
		{"fieldname": "litres", "label": _("Litres"), "fieldtype": "Float", "precision": 1, "width": 90},
		{"fieldname": "cost", "label": _("Fuel Cost"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "worked_hours", "label": _("Worked Hours"), "fieldtype": "Float", "precision": 1, "width": 110},
		{"fieldname": "lph", "label": _("L / h"), "fieldtype": "Float", "precision": 2, "width": 80},
		{"fieldname": "norm", "label": _("Norm L / h"), "fieldtype": "Float", "precision": 2, "width": 95},
		{"fieldname": "variance", "label": _("vs Norm %"), "fieldtype": "Float", "precision": 1, "width": 95},
		{"fieldname": "flag", "label": _("Flag"), "fieldtype": "Data", "width": 190},
	]


def summary(rows):
	flagged = [r for r in rows if r["flag"]]
	return [
		{"label": _("Litres issued"), "value": flt(sum(r["litres"] for r in rows), 1), "datatype": "Float"},
		{"label": _("Fuel cost"), "value": sum(r["cost"] for r in rows), "datatype": "Currency"},
		{"label": _("Worked hours"), "value": flt(sum(r["worked_hours"] for r in rows), 1), "datatype": "Float"},
		{"label": _("Machines flagged"), "value": len(flagged), "datatype": "Int", "indicator": "Red" if flagged else "Green"},
	]
