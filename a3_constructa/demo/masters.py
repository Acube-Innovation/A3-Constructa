# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Demo masters: the project, its cost structure, and the things it buys."""

import frappe
from frappe.utils import flt

from a3_constructa.demo.common import (
	COST_HEADS,
	PREFIX,
	PROJECT_NAME,
	abbr,
	account,
	company,
	day,
	ensure,
	ensure_by,
	log,
	warehouse,
)

# (code, name, serialised, uom, item group, rate, is stock item)
ITEMS = [
	("MBK-CEM-42", "Cement OPC 42.5N (50kg)", 0, "Nos", "Construction Materials", 12.0, 1),
	("MBK-REBAR-16", "Reinforcement Bar 16mm", 0, "Nos", "Construction Materials", 28.0, 1),
	("MBK-BLOCK-200", "Hollow Block 200mm", 0, "Nos", "Construction Materials", 1.6, 1),
	("MBK-AGG-20", "Coarse Aggregate 20mm (m3)", 0, "Nos", "Construction Materials", 34.0, 1),
	("MBK-SCAF-SET", "Scaffolding Set", 0, "Nos", "Temporary Works", 210.0, 1),
	("MBK-TOOL-DRILL", "Hammer Drill", 1, "Nos", "Small Tools", 380.0, 1),
	("MBK-TOOL-LEVEL", "Laser Level", 1, "Nos", "Small Tools", 640.0, 1),
	("MBK-SPR-FILTER", "Hydraulic Filter - Excavator", 0, "Nos", "Spare Parts", 95.0, 1),
	("MBK-SVC-BLOCK", "Blockwork Subcontract (m2)", 0, "Nos", "Subcontract Works", 22.0, 0),
	("MBK-SVC-TRANS", "Inland Haulage per Trip", 0, "Nos", "Transport", 450.0, 0),
	("MBK-RENT-CRANE", "Mobile Crane Hire (day)", 0, "Nos", "Rental Equipment", 780.0, 0),
]

# (code, description, category, wbs key, account hint)
COST_CODES = [
	("MBK-CC-SUB", "Substructure concrete and rebar", "Material", "MBK-W-SUB", "Cost of Goods"),
	("MBK-CC-SUP", "Superstructure frame", "Material", "MBK-W-SUP", "Cost of Goods"),
	("MBK-CC-BLK", "Blockwork subcontract", "Subcontract", "MBK-W-SUP", "Cost of Goods"),
	("MBK-CC-TMP", "Temporary works and scaffolding", "Material", "MBK-W-TMP", "Cost of Goods"),
	("MBK-CC-PLT", "Plant and equipment", "Rental", "MBK-W-SUP", "Cost of Goods"),
]


def run():
	grant_demo_roles()
	create_project()
	create_cost_heads()
	create_wbs()
	create_cost_codes()
	create_warehouses()
	create_locations()
	create_supplier_groups_and_suppliers()
	create_items()
	create_logistics_masters()
	create_employees()
	frappe.db.commit()


# --------------------------------------------------------------------- project
def create_project():
	if frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name"):
		log("project already present")
		return
	doc = ensure_by("Project", {"project_name": PROJECT_NAME}, {
		"doctype": "Project", "project_name": PROJECT_NAME, "status": "Open",
		"company": company(), "expected_start_date": day(-120),
		"expected_end_date": day(420), "project_type": "External",
		"percent_complete_method": "Manual",
	})
	log("project %s" % doc.name)


def _project():
	return frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")


# ------------------------------------------------------------------ cost heads
def create_cost_heads():
	"""The five packages head 3 of the sheet names, as a tree under the project."""
	cost_center = frappe.get_all(
		"Cost Center", filters={"company": company(), "is_group": 0}, pluck="name"
	)
	cc = cost_center[0] if cost_center else None

	for idx, name in enumerate(COST_HEADS, start=1):
		code = "%s-CH-%02d" % (PREFIX, idx)
		ensure("Cost Head", code, {
			"doctype": "Cost Head", "cost_head_code": code, "cost_head_name": name,
			"project": _project(), "cost_center": cc, "is_group": 0, "status": "Active",
		})
	log("cost heads: %s" % ", ".join(COST_HEADS))


def university_head():
	return frappe.db.get_value("Cost Head", {"cost_head_name": "University"}, "name")


# ------------------------------------------------------------------------ wbs
WBS_NODES = [
	("MBK-W-ALL", "Mbandaka Campus", None, 1),
	("MBK-W-SUB", "Substructure", "MBK-W-ALL", 0),
	("MBK-W-SUP", "Superstructure", "MBK-W-ALL", 0),
	("MBK-W-TMP", "Temporary Works", "MBK-W-ALL", 0),
]


def create_wbs():
	for code, name, parent, is_group in WBS_NODES:
		ensure("WBS", code, {
			"doctype": "WBS", "wbs_code": code, "wbs_name": name,
			"parent_wbs": parent, "is_group": is_group, "project": _project(),
			"cost_head": university_head(), "status": "Active",
		})
	log("WBS tree: %d nodes" % len(WBS_NODES))


# ----------------------------------------------------------------- cost codes
def create_cost_codes():
	cost_center = frappe.get_all(
		"Cost Center", filters={"company": company(), "is_group": 0}, pluck="name"
	)
	cc = cost_center[0] if cost_center else None
	expense = account("", hint="Cost of Goods", root_type="Expense") or account(
		"", root_type="Expense"
	)

	for code, description, category, wbs, _hint in COST_CODES:
		ensure("Cost Code", code, {
			"doctype": "Cost Code", "cost_code": code, "description": description,
			"category": category, "wbs": wbs, "account": expense, "cost_center": cc,
			"uom": "Nos", "status": "Active",
		})
	log("cost codes: %d" % len(COST_CODES))


# ----------------------------------------------------------------- warehouses
def create_warehouses():
	parent = frappe.db.get_value(
		"Warehouse", {"company": company(), "is_group": 1}, "name"
	)
	for short, wtype in [("MBK Central Store", None), ("MBK Site Store", "Site"),
	                     ("MBK Transit", "Transit"), ("MBK Tool Custody", "Custody")]:
		ensure("Warehouse", warehouse(short), {
			"doctype": "Warehouse", "warehouse_name": short, "company": company(),
			"parent_warehouse": parent, "warehouse_type": wtype,
		})
	log("warehouses: central, site, transit, custody")


# ------------------------------------------------------------------- suppliers
SUPPLIERS = [
	("MBK Cement Works", "Raw Material"),
	("MBK Steel Traders", "Raw Material"),
	("MBK Blockwork Subcontractor", "Services"),
	("Congo River Lines", "Shipping Line"),
	("Matadi Clearing Agents", "Freight Forwarder"),
	("MBK Inland Haulage", "Services"),
]


def create_supplier_groups_and_suppliers():
	# Head 13 of the sheet splits suppliers by these two groups, and the
	# Shipping Lines / Freight Forwarders reports filter on them.
	root = frappe.db.get_value("Supplier Group", {"is_group": 1}, "name") or "All Supplier Groups"
	for group in ["Shipping Line", "Freight Forwarder"]:
		ensure("Supplier Group", group, {
			"doctype": "Supplier Group", "supplier_group_name": group,
			"parent_supplier_group": root, "is_group": 0,
		})

	for name, group in SUPPLIERS:
		ensure("Supplier", name, {
			"doctype": "Supplier", "supplier_name": name, "supplier_group": group,
			"supplier_type": "Company", "country": frappe.db.get_value(
				"Company", company(), "country") or "India",
		})
	log("suppliers: %d (incl. shipping line and forwarder)" % len(SUPPLIERS))


# ----------------------------------------------------------------------- items
def create_items():
	for code, name, serialised, uom, group, rate, is_stock in ITEMS:
		item = ensure("Item", code, {
			"doctype": "Item", "item_code": code, "item_name": name,
			"item_group": group, "stock_uom": uom, "is_stock_item": is_stock,
			"has_serial_no": serialised,
			"serial_no_series": "TOOL-.####" if serialised else None,
			"valuation_rate": rate, "lead_time_days": 21,
			"is_mas": 1 if group == "Construction Materials" else 0,
			"description": name,
		})
		if serialised and not item.get("serial_no_series"):
			frappe.db.set_value("Item", item.name, "serial_no_series", "TOOL-.####")
	log("items: %d across %d item groups" % (
		len(ITEMS), len({i[4] for i in ITEMS})))


# ------------------------------------------------------------ logistics masters
def create_logistics_masters():
	ensure("Port", "Shanghai", {
		"doctype": "Port", "port_name": "Shanghai", "port_code": "CNSHA",
		"port_type": "Sea", "is_active": 1,
	})
	ensure("Port", "Matadi", {
		"doctype": "Port", "port_name": "Matadi", "port_code": "CDMAT",
		"port_type": "Sea", "is_active": 1,
	})
	ensure("Service Route", "Shanghai - Matadi", {
		"doctype": "Service Route", "route_name": "Shanghai - Matadi",
		"origin_port": "Shanghai", "discharge_port": "Matadi",
		"mode_of_transport": "Sea", "transit_days": 42,
		"shipping_line": "Congo River Lines",
	})
	ensure_by("Freight Rate Contract",
	          {"supplier": "Congo River Lines", "service_route": "Shanghai - Matadi"}, {
		"doctype": "Freight Rate Contract", "supplier": "Congo River Lines",
		"service_route": "Shanghai - Matadi", "container_type": "40FT",
		"rate": 3200, "currency": frappe.db.get_value("Company", company(), "default_currency"),
		"free_days": 14, "valid_from": day(-180), "valid_to": day(180), "status": "Active",
	})
	log("ports, service route and freight rate contract")


# ------------------------------------------------------------------- employees
EMPLOYEES = [
	("Jean", "Mukendi", "Site Engineer"),
	("Alice", "Kabeya", "Quantity Surveyor"),
	("Paul", "Ilunga", "Store Keeper"),
	("Grace", "Mbuyi", "Plant Operator"),
]


def create_employees():
	if not frappe.db.get_value("HR Settings", None, "emp_created_by"):
		frappe.db.set_single_value("HR Settings", "emp_created_by", "Naming Series")
		frappe.db.commit()

	for first, last, designation in EMPLOYEES:
		full = "%s %s" % (first, last)
		ensure("Designation", designation, {
			"doctype": "Designation", "designation_name": designation,
		})
		ensure_by("Employee", {"employee_name": full}, {
			"doctype": "Employee", "first_name": first, "last_name": last,
			"company": company(), "gender": "Female" if first in ("Alice", "Grace") else "Male",
			"date_of_birth": "1990-01-01", "date_of_joining": day(-400),
			"designation": designation, "status": "Active",
		})
	log("employees: %d" % len(EMPLOYEES))


def employee(full_name: str) -> str:
	return frappe.db.get_value("Employee", {"employee_name": full_name}, "name")


# The workflow transitions are role-gated, and so are the app's doctypes. A demo
# is run as Administrator, who holds no A3 Constructa roles by default, so the
# BOQ approval would be refused. Granting them here also means the person giving
# the demo sees the app the way its intended users will.
A3_ROLES = [
	"A3 Constructa Admin", "Constructa Project Manager", "Constructa Site Engineer",
	"Constructa Quantity Surveyor", "Constructa Store Keeper",
]


def grant_demo_roles():
	user = frappe.get_doc("User", "Administrator")
	held = {r.role for r in user.roles}
	missing = [r for r in A3_ROLES if r not in held and frappe.db.exists("Role", r)]
	if not missing:
		return
	for role in missing:
		user.append("roles", {"role": role})
	user.flags.ignore_permissions = True
	user.save()
	log("granted Administrator: %s" % ", ".join(missing))


# Head 12 of the sheet keeps project sites as Locations, and an Asset with a
# custodian needs one to be received into.
LOCATIONS = [
	("Mbandaka Campus Site", None),
	("Mbandaka Main Compound", "Mbandaka Campus Site"),
	("Mbandaka Laydown Area", "Mbandaka Campus Site"),
]


def create_locations():
	for name, parent in LOCATIONS:
		ensure("Location", name, {
			"doctype": "Location", "location_name": name,
			"parent_location": parent, "is_group": 1 if parent is None else 0,
		})
	log("locations: %d" % len(LOCATIONS))
