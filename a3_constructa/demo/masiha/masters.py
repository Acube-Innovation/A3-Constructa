# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Step 1, the masters: the client, the project, its cost structure, and what it buys.

The cost structure is the client's own diagram: three cost heads, the
Architectural head developed into work packages, and the Flooring package into
WBS A (ground-floor porcelain) and WBS B (first-floor porcelain).
"""

import frappe

from a3_constructa.demo.masiha.common import (
	BUYING_PRICE_LIST,
	COMPANY,
	CUSTOMER,
	PROJECT_NAME,
	acc,
	cost_center,
	day,
	exists,
	insert,
	log,
	project,
	user,
	wh,
)

# ------------------------------------------------------------------ cost heads
# (code, name, parent, is group)
COST_HEADS = [
	("MSS-ES", "Earthworks / Structural", None, 0),
	("MSS-AR", "Architectural", None, 1),
	("MSS-AR-DW", "Doors & Windows", "MSS-AR", 0),
	("MSS-AR-FL", "Flooring", "MSS-AR", 0),
	("MSS-AR-PT", "Painting", "MSS-AR", 0),
	("MSS-MEP", "MEP / Others / Misc.", None, 0),
]

# (code, name, parent, cost head, is group)
WBS = [
	("MSS-W", "Mbandaka Administrative Centre", None, None, 1),
	("MSS-W-ES", "Substructure and frame", "MSS-W", "MSS-ES", 0),
	("MSS-W-AR", "Architectural works", "MSS-W", "MSS-AR", 1),
	("MSS-W-DW", "Doors and windows", "MSS-W-AR", "MSS-AR-DW", 0),
	("MSS-W-FL", "Flooring", "MSS-W-AR", "MSS-AR-FL", 1),
	("MSS-W-FL-A", "WBS A: Ground-floor porcelain", "MSS-W-FL", "MSS-AR-FL", 0),
	("MSS-W-FL-B", "WBS B: First-floor porcelain", "MSS-W-FL", "MSS-AR-FL", 0),
	("MSS-W-PT", "Painting", "MSS-W-AR", "MSS-AR-PT", 0),
	("MSS-W-MEP", "MEP installations", "MSS-W", "MSS-MEP", 0),
]

# (code, description, category, account)
COST_CODES = [
	("MSS-CC-FIN-M", "Floor finishes - materials", "Material", "Project Materials"),
	("MSS-CC-FIN-S", "Floor finishes - installation", "Service", "Project Services"),
	("MSS-CC-STR-M", "Structure - concrete and steel", "Material", "Project Materials"),
	("MSS-CC-DW-M", "Doors and windows - supply", "Material", "Project Materials"),
	("MSS-CC-PNT-M", "Painting - materials", "Material", "Project Materials"),
	("MSS-CC-MEP-M", "MEP - materials", "Material", "Project Materials"),
	("MSS-CC-SITE", "Site consumables and small tools", "Spare", "Project Materials"),
	("MSS-CC-PLT", "Plant and equipment", "Rental", "Plant and Equipment Costs"),
]

# ------------------------------------------------------------------ item classes
# The approved classification: every item code carries its class prefix, so a
# new code is checked against its class before it is created.
ITEM_GROUPS = [
	("Floor and Wall Finishes", "FIN"),
	("Cement and Concrete", "CEM"),
	("Reinforcement Steel", "STL"),
	("Doors and Windows", "DW"),
	("Paints and Coatings", "PNT"),
	("Electrical Materials", "ELE"),
	("Heavy Equipment Items", "EQ"),
	("Contract Works", "CW"),
]

# (code, name, group, uom, stock item, rate, extra)
ITEMS = [
	("FIN-POR-600", "Porcelain floor tile 600x600 mm, matt, R10", "Floor and Wall Finishes", "Square Meter", 1, 18.50,
	 {"customs_tariff_number": "69072100", "lead_time_days": 60, "country_of_origin": "Spain"}),
	("FIN-ADH-C2", "Tile adhesive C2TE, 25 kg", "Floor and Wall Finishes", "Bag", 1, 9.80,
	 {"customs_tariff_number": "32149000", "lead_time_days": 60}),
	("FIN-GRT-CG2", "Tile grout CG2, 5 kg", "Floor and Wall Finishes", "Bag", 1, 6.40,
	 {"customs_tariff_number": "32149000", "lead_time_days": 60}),
	("FIN-SPC-3", "Tile spacers 3 mm, box of 500", "Consumables", "Box", 1, 4.50, {}),
	("FIN-DSC-230", "Diamond cutting disc 230 mm", "Consumables", "Nos", 1, 22.00, {}),
	("SVC-TILE-INST", "Tile installation, labour and tools", "Installation", "Square Meter", 0, 7.50, {}),
	("CEM-425-50", "Cement CEM II 42.5N, 50 kg", "Cement and Concrete", "Bag", 1, 11.20, {"lead_time_days": 7}),
	("STL-Y16", "Reinforcement bar Y16", "Reinforcement Steel", "Tonne", 1, 980.00, {"lead_time_days": 14}),
	("DW-ALW-1215", "Aluminium window 1200x1500, double glazed", "Doors and Windows", "Nos", 1, 410.00, {}),
	("DW-DOR-FD90", "Fire door 900 mm, FD60", "Doors and Windows", "Nos", 1, 680.00, {}),
	("PNT-EMU-20", "Emulsion paint, interior, 20 L pail", "Paints and Coatings", "Nos", 1, 64.00, {}),
	("ELE-CBL-4", "Copper cable 4 mm2", "Electrical Materials", "Meter", 1, 1.35, {}),
	("EQ-EXC-20T", "Excavator 20 t", "Heavy Equipment Items", "Nos", 0, 145000.00,
	 {"is_fixed_asset": 1, "asset_category": "Heavy Equipment", "auto_create_assets": 1,
	  "asset_naming_series": "HEQ-.####"}),
	# What the client is billed for: the awarded works, one line per cost head.
	("CW-STRUCT", "Contract works - earthworks and structure", "Contract Works", "Nos", 0, 0, {"is_purchase_item": 0}),
	("CW-ARCH", "Contract works - architectural", "Contract Works", "Nos", 0, 0, {"is_purchase_item": 0}),
	("CW-MEP", "Contract works - MEP", "Contract Works", "Nos", 0, 0, {"is_purchase_item": 0}),
]

# (name, group, country, currency, payment terms)
SUPPLIERS = [
	("Iberica Ceramica S.L.", "International Suppliers", "Spain", "EUR", "30% Advance, 70% on Delivery"),
	("Foshan Tile Export Co. Ltd.", "International Suppliers", "China", "USD", "30% Advance, 70% on Delivery"),
	("Kinshasa Building Supplies SARL", "Local Suppliers", "Congo, The Democratic Republic of the", "USD", "Net 30 Days"),
	("Congo Steel & Cement SARL", "Local Suppliers", "Congo, The Democratic Republic of the", "USD", "Net 30 Days"),
	("Equipements Lourds du Congo SARL", "Equipment Suppliers", "Congo, The Democratic Republic of the", "USD", "Net 30 Days"),
	("Quincaillerie du Fleuve", "Local Suppliers", "Congo, The Democratic Republic of the", "USD", None),
	("Oceanis Shipping Lines", "Shipping Line", "France", "USD", "Net 30 Days"),
	("Matadi Clearing & Forwarding SARL", "Freight Forwarder", "Congo, The Democratic Republic of the", "USD", "Net 30 Days"),
	("Fleuve Congo Barges SARL", "Transporter", "Congo, The Democratic Republic of the", "USD", "Net 30 Days"),
]


def run():
	create_expense_accounts()
	create_customer()
	create_locations()
	create_project()
	create_cost_heads()
	create_wbs()
	create_cost_codes()
	create_warehouses()
	create_item_groups()
	create_tariffs()
	create_items()
	request_new_item()
	create_suppliers()
	create_logistics_masters()
	create_approval_matrix()
	frappe.db.commit()


def create_expense_accounts():
	for name in ("Project Materials", "Project Services", "Plant and Equipment Costs"):
		if not frappe.db.exists("Account", acc(name)):
			insert({"doctype": "Account", "account_name": name, "company": COMPANY,
			        "parent_account": acc("Direct Expenses"), "account_type": "Expense Account"})
	# Imports are invoiced in euros, so the Spanish supplier needs a euro payable.
	if not frappe.db.exists("Account", acc("Creditors EUR")):
		insert({"doctype": "Account", "account_name": "Creditors EUR", "company": COMPANY,
		        "parent_account": acc("Accounts Payable"), "account_type": "Payable", "account_currency": "EUR"})
	log("project expense accounts and a euro payable")


def create_customer():
	if not frappe.db.exists("Customer", CUSTOMER):
		insert({"doctype": "Customer", "customer_name": CUSTOMER, "customer_group": "Government",
		        "territory": "All Territories", "customer_type": "Company", "default_currency": "USD"})
	log(f"client {CUSTOMER}")


def create_locations():
	for name in ("Kinshasa Central Yard", "Mbandaka Site"):
		if not frappe.db.exists("Location", name):
			insert({"doctype": "Location", "location_name": name})


def create_project():
	if project():
		log("project already present")
		return
	doc = insert({
		"doctype": "Project", "project_name": PROJECT_NAME, "company": COMPANY, "customer": CUSTOMER,
		"status": "Open", "project_type": "External", "expected_start_date": day(-140),
		"expected_end_date": day(220), "location": "Mbandaka Site", "cost_center": cost_center(),
		"percent_complete_method": "Manual",
		"notes": "Design & Build. Project manager: Didier Kasongo.",
		"users": [{"user": user("pm")}, {"user": user("qs")}, {"user": user("requester")}],
	})
	log(f"project {doc.name}: {PROJECT_NAME}")


def create_cost_heads():
	for code, name, parent, is_group in COST_HEADS:
		if frappe.db.exists("Cost Head", code):
			continue
		insert({"doctype": "Cost Head", "cost_head_code": code, "cost_head_name": name,
		        "parent_cost_head": parent, "is_group": is_group, "project": project(),
		        "cost_center": cost_center(), "status": "Active"})
	log("cost heads: Earthworks / Structural, Architectural (Doors & Windows, Flooring, Painting), MEP")


def create_wbs():
	for code, name, parent, head, is_group in WBS:
		if frappe.db.exists("WBS", code):
			continue
		insert({"doctype": "WBS", "wbs_code": code, "wbs_name": name, "parent_wbs": parent,
		        "cost_head": head, "is_group": is_group, "project": project(), "status": "Active"})
	log("WBS tree: 9 nodes, Flooring split into WBS A (ground floor) and WBS B (first floor)")


def create_cost_codes():
	for code, description, category, account in COST_CODES:
		if frappe.db.exists("Cost Code", code):
			continue
		insert({"doctype": "Cost Code", "cost_code": code, "description": description, "category": category,
		        "account": acc(account), "cost_center": cost_center(), "status": "Active"})
	log(f"cost codes: {len(COST_CODES)}, each posting to its project expense account")


def create_item_groups():
	for name, _prefix in ITEM_GROUPS:
		if not frappe.db.exists("Item Group", name):
			insert({"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups",
			        "is_group": 0})


def create_tariffs():
	for number, description, duty in (("69072100", "Ceramic tiles, porcelain, water absorption <= 0.5%", 20),
	                                  ("32149000", "Mastics, tile adhesives and grouts", 10)):
		if not frappe.db.exists("Customs Tariff Number", number):
			insert({"doctype": "Customs Tariff Number", "tariff_number": number, "description": description,
			        "duty_percentage": duty, "duty_account": acc("Import Freight and Clearing")})


def create_items():
	for code, name, group, uom, stock, rate, extra in ITEMS:
		if not frappe.db.exists("Item", code):
			insert({"doctype": "Item", "item_code": code, "item_name": name, "description": name,
			        "item_group": group, "stock_uom": uom, "is_stock_item": stock, "is_purchase_item": 1,
			        "is_sales_item": 1 if group == "Contract Works" else 0, "valuation_rate": rate,
			        # Given even for services: ERPNext would otherwise fill in the site-wide
			        # default store, which belongs to another company.
			        "item_defaults": [{"company": COMPANY, "default_warehouse": wh("Central Store Kinshasa")}],
			        **extra})
		if rate and not exists("Item Price", {"item_code": code, "price_list": BUYING_PRICE_LIST}):
			insert({"doctype": "Item Price", "item_code": code, "price_list": BUYING_PRICE_LIST,
			        "price_list_rate": rate})
	log(f"items: {len(ITEMS)} (materials, services, an asset item, contract works), coded by class")


def request_new_item():
	"""Step 4: a new item asked for when nothing suitable exists.

	It is created disabled, so nobody can buy it, and the master-data owner
	enables it once the specification is approved.
	"""
	code = "FIN-POR-600-R11"
	if frappe.db.exists("Item", code):
		return
	insert({"doctype": "Item", "item_code": code, "item_name": "Porcelain floor tile 600x600 mm, anti-slip R11",
	        "description": "Requested for wet areas (toilets, kitchen). Pending master data approval.",
	        "item_group": "Floor and Wall Finishes", "stock_uom": "Square Meter", "is_stock_item": 1,
	        "is_purchase_item": 1, "disabled": 1,
	        "item_defaults": [{"company": COMPANY, "default_warehouse": wh("Central Store Kinshasa")}]})
	frappe.get_doc("Item", code).add_comment(
		"Comment", "New item request from Esther Ngalula (QS): wet areas need R11 anti-slip; "
		"FIN-POR-600 is R10 only. Awaiting approval by master data before it can be requested.")
	log("new item request FIN-POR-600-R11, disabled until approved")


def create_suppliers():
	for group in ("International Suppliers", "Local Suppliers", "Equipment Suppliers", "Shipping Line",
	              "Freight Forwarder", "Transporter"):
		if not frappe.db.exists("Supplier Group", group):
			insert({"doctype": "Supplier Group", "supplier_group_name": group,
			        "parent_supplier_group": "All Supplier Groups"})
	for name, group, country, currency, terms in SUPPLIERS:
		if frappe.db.exists("Supplier", name):
			continue
		accounts = [{"company": COMPANY, "account": acc("Creditors EUR")}] if currency == "EUR" else []
		insert({"doctype": "Supplier", "supplier_name": name, "supplier_group": group, "country": country,
		        "default_currency": currency, "payment_terms": terms, "accounts": accounts})
	log(f"suppliers: {len(SUPPLIERS)} (international, local, cash, shipping, clearing, barge)")


def create_warehouses():
	parent = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 1}, "name")
	for short, wtype in (("Central Store Kinshasa", None), ("Mbandaka Site Store", "Site"),
	                     ("Rejected Goods", None)):
		if not frappe.db.exists("Warehouse", wh(short)):
			insert({"doctype": "Warehouse", "warehouse_name": short, "company": COMPANY,
			        "parent_warehouse": parent, "warehouse_type": wtype})
	log("stores: Central Store Kinshasa, Mbandaka Site Store, Goods In Transit, Rejected Goods")


def create_logistics_masters():
	for name, code, country, kind in (("Valencia", "ESVLC", "Spain", "Sea"), ("Matadi", "CDMAT", COUNTRY_DRC, "Sea"),
	                                  ("Kinshasa River Port", "CDFIH", COUNTRY_DRC, "Inland"),
	                                  ("Mbandaka River Port", "CDMDK", COUNTRY_DRC, "Inland")):
		if not frappe.db.exists("Port", name):
			insert({"doctype": "Port", "port_name": name, "port_code": code, "country": country,
			        "port_type": kind, "is_active": 1})
	for route, origin, discharge, mode, days, line in (
		("Valencia - Matadi", "Valencia", "Matadi", "Sea", 28, "Oceanis Shipping Lines"),
		("Kinshasa - Mbandaka (barge)", "Kinshasa River Port", "Mbandaka River Port", "Multimodal", 9,
		 "Fleuve Congo Barges SARL"),
	):
		if not frappe.db.exists("Service Route", route):
			insert({"doctype": "Service Route", "route_name": route, "origin_port": origin,
			        "discharge_port": discharge, "mode_of_transport": mode, "transit_days": days,
			        "shipping_line": line})
	if not exists("Freight Rate Contract", {"supplier": "Oceanis Shipping Lines"}):
		insert({"doctype": "Freight Rate Contract", "supplier": "Oceanis Shipping Lines",
		        "service_route": "Valencia - Matadi", "container_type": "40FT", "rate": 3400, "currency": "USD",
		        "free_days": 14, "valid_from": day(-160), "valid_to": day(200), "status": "Active"})

	for name, category in (("Commercial Invoice", "Commercial"), ("Packing List", "Commercial"),
	                       ("Bill of Lading", "Commercial")):
		if not frappe.db.exists("Document Type", name):
			insert({"doctype": "Document Type", "document_type_name": name, "document_category": category,
			        "is_mandatory": 1, "applicable_for": "Shipment Tracking"})
	if not exists("Mandatory Document Rule", {"reference_doctype": "Shipment Tracking", "transaction_type": "Import"}):
		insert({"doctype": "Mandatory Document Rule", "reference_doctype": "Shipment Tracking",
		        "transaction_type": "Import", "applicable_project": project(), "is_blocking": 1,
		        "document_type": [{"document_type": d} for d in (
		            "Commercial Invoice", "Packing List", "Bill of Lading", "Certificate of Origin",
		            "Duty Payment Receipt")]})
	log("ports, Valencia-Matadi sea route and freight contract, barge route, import document rule")


COUNTRY_DRC = "Congo, The Democratic Republic of the"


def create_approval_matrix():
	rules = [
		("Material Request", 0, 10000, 1, "Constructa Project Manager"),
		("Material Request", 10000, 100000, 2, "Purchase Manager"),
		("Material Request", 100000, 0, 3, "A3 Constructa Admin"),
		("Purchase Order", 0, 25000, 1, "Purchase Manager"),
		("Purchase Order", 25000, 0, 2, "A3 Constructa Admin"),
	]
	for doctype, low, high, level, role in rules:
		if exists("Approval Matrix", {"reference_doctype": doctype, "approval_level": level, "project": project()}):
			continue
		insert({"doctype": "Approval Matrix", "reference_doctype": doctype, "project": project(),
		        "amount_from": low, "amount_to": high, "approval_level": level, "approver_role": role,
		        "is_active": 1})
	log("approval matrix: requests in three value bands, orders in two")
