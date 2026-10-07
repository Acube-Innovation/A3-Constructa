# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Fuel issued to machines - catalogue 8.4.

A fuel line (an item in the Fuel item group, or a group under it) on a material
issue names the machine it went into (Stock Entry Detail.asset) and, if read,
its meter. Each machine's Equipment Log for the day carries the litres issued to
it that day (fuel_litres), kept as issues are submitted and cancelled. The Fuel
Consumption report sets litres against worked hours and the machine's norm.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

FUEL_GROUP = "Fuel"
ISSUES = ("Material Issue",)


def fuel_groups() -> list[str]:
	lft, rgt = frappe.db.get_value("Item Group", FUEL_GROUP, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return []
	return frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name")


def is_fuel(item_code, groups=None) -> bool:
	groups = fuel_groups() if groups is None else groups
	return bool(groups) and frappe.db.get_value("Item", item_code, "item_group") in groups


def validate(doc, method=None):
	groups = fuel_groups()
	if not groups:
		return
	for row in doc.items:
		fuel = is_fuel(row.item_code, groups)
		if not fuel:
			if row.get("asset") or row.get("meter_reading"):
				row.asset, row.meter_reading = None, None
			continue
		if doc.purpose in ISSUES and row.s_warehouse and not row.t_warehouse and not row.asset:
			frappe.throw(_("Row {0}: {1} is fuel - name the machine it went into.").format(row.idx, row.item_name or row.item_code),
			             title=_("Fuel issue"))
		if row.asset and flt(row.meter_reading):
			last = flt(frappe.db.get_value("Asset", row.asset, "current_meter"))
			if flt(row.meter_reading) < last:
				frappe.msgprint(_("Row {0}: meter {1} is below {2}'s last reading of {3}.").format(
					row.idx, flt(row.meter_reading), row.asset, last), indicator="orange", alert=True)


def fuel_for(asset, on) -> float:
	groups = fuel_groups()
	if not groups:
		return 0.0
	return flt(frappe.db.sql("""select sum(d.transfer_qty) from `tabStock Entry Detail` d join `tabStock Entry` se on se.name = d.parent
		join `tabItem` i on i.name = d.item_code
		where se.docstatus = 1 and se.purpose in %s and d.asset = %s and se.posting_date = %s and i.item_group in %s""",
	                         (ISSUES, asset, getdate(on), groups))[0][0], 3)


def update_logs(doc, method=None):
	"""Fuel issued or cancelled: refresh the machines' logs for that day."""
	for asset in {r.asset for r in doc.items if r.get("asset")}:
		litres = fuel_for(asset, doc.posting_date)
		for name in frappe.get_all("Equipment Log", filters={"asset": asset, "log_date": doc.posting_date, "docstatus": ["<", 2]}, pluck="name"):
			frappe.db.set_value("Equipment Log", name, "fuel_litres", litres, update_modified=False)
