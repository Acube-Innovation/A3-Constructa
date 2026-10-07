# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-08B: fuel issued per machine, and the equipment the programme needs.

Diesel (item group Fuel) is received into the Mbandaka site store and issued to
the machines on the days they worked, each line naming the machine and its meter:
- the 20 t excavator (norm 14 L/h) burns about 14.6 L/h - within 15%;
- the hired concrete mixer (norm 1.6 L/h) takes about 2.1 L/h - 30% over:
  flagged (the plant foreman is checking for a leak on the fuel line).

The programme's machines:
- the hospital's foundation excavation names the excavator, which is on the
  Administrative Centre: it has to move, and the Administrative Centre's
  external works want it on the same days (a double booking);
- the hospital substructure and the committee wing's air-conditioning need
  small machinery the projects don't have; the mixer is idle at the
  Administrative Centre those weeks.
"""

import frappe
from frappe.utils import add_days, flt, getdate

from a3_constructa.demo.masiha.common import COMPANY, as_user, at, comment, insert, log, project, wh

DIESEL = "FUEL-DSL"
EXCAVATOR = "HEQ-0001"
MIXER_ITEM = "EQ-MIX-350"
# asset: (norm L/h, litres per worked hour issued)
NORMS = {EXCAVATOR: (14, 14.6), "mixer": (1.6, 2.1), "HEQ-0002": (12, None)}


def run():
	masters()
	mixer = frappe.db.get_value("Asset", {"item_code": MIXER_ITEM}, "name")
	for asset, (norm, _rate) in NORMS.items():
		frappe.db.set_value("Asset", mixer if asset == "mixer" else asset, "fuel_norm_lph", norm, update_modified=False)
	plan_rows()
	if frappe.db.exists("Stock Entry Detail", {"item_code": DIESEL}):
		log("fuel issues already present")
		return
	logs = frappe.get_all("Equipment Log", filters={"docstatus": 1, "asset": ["in", [EXCAVATOR, mixer]], "worked_hours": [">", 0]},
	                      fields=["asset", "log_date", "worked_hours", "meter_end", "project"], order_by="log_date")
	first = min(getdate(l.log_date) for l in logs)
	insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
	        "posting_date": add_days(first, -7), "set_posting_time": 1, "project": project(),
	        "remarks": "Diesel delivered by tanker to the site tank.",
	        "items": [{"item_code": DIESEL, "qty": 3000, "t_warehouse": wh("Mbandaka Site Store"), "basic_rate": 1.40,
	                   "project": project()}]}, submit=True)
	litres = 0
	with as_user("stores"):
		for l in logs:
			rate = NORMS["mixer" if l.asset == mixer else l.asset][1]
			qty = round(flt(l.worked_hours) * rate)
			litres += qty
			insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Issue Note (MIN)", "purpose": "Material Issue",
			        "posting_date": l.log_date, "set_posting_time": 1, "project": l.project,
			        "remarks": "Fuel issued from the site tank.",
			        "items": [{"item_code": DIESEL, "qty": qty, "s_warehouse": wh("Mbandaka Site Store"), "project": l.project,
			                   "cost_code": "MSS-CC-EQP", "asset": l.asset, "meter_reading": l.meter_end}]}, submit=True)
	comment("Asset", mixer, "Using more diesel than it should: the fuel line is being checked for a leak.", "pm", at(-1, 16))
	log(f"Fuel: 3,000 L received; {litres} L issued over {len(logs)} machine-days; norms on the excavator, mixer and crane")


def masters():
	if not frappe.db.exists("Item Group", "Fuel"):
		insert({"doctype": "Item Group", "item_group_name": "Fuel", "parent_item_group": "All Item Groups"})
	if not frappe.db.exists("Item", DIESEL):
		insert({"doctype": "Item", "item_code": DIESEL, "item_name": "Diesel (gasoil)", "item_group": "Fuel", "stock_uom": "Litre",
		        "is_stock_item": 1, "valuation_rate": 1.40, "include_item_in_manufacturing": 0,
		        "item_defaults": [{"company": COMPANY, "default_warehouse": wh("Mbandaka Site Store")}]})


def plan_rows():
	"""The Administrative Centre's external works want the excavator over the hospital's excavation."""
	t = frappe.db.get_value("Task", {"project": project(), "subject": "Finishes and handover"})
	doc = frappe.get_doc("Task", t)
	if any(r.asset == EXCAVATOR for r in doc.resources):
		return
	doc.append("resources", {"resource_type": "Equipment", "asset": EXCAVATOR, "description": "Excavator: external drainage and paving",
	                         "qty_per_day": 1, "days": 20})
	frappe.flags.a3_no_reschedule = 1
	try:
		doc.flags.ignore_permissions = True
		doc.save()
	finally:
		frappe.flags.a3_no_reschedule = 0
