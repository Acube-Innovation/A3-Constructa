# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""The records the story never needed, so that every list a tester opens has rows.

Fifteen open leads for the sales team to work through, addresses on the client
and the main suppliers, support issues raised by the client, spare parts listed
against the excavator, small tools out with the site team (one overdue), and
the attic stock of floor tiles delivered to the client at handover.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, as_user, at, day, exists, insert, log, project, user, wh

# (organisation, contact first, last, sector, channel, value, tender due day, email)
OPEN_LEADS = [
	("Clinique Saint-Joseph de Mbandaka", "Thérèse", "Bompoko", "Healthcare", "Referral", 640_000, 25, "t.bompoko@csj-mbandaka.cd"),
	("Institut Supérieur Pédagogique de Mbandaka", "Prosper", "Ilonga", "Education", "Tender portal", 980_000, 33, "p.ilonga@isp-mbandaka.cd"),
	("Banque Commerciale du Congo, agence Equateur", "Nadine", "Lokuli", "Commercial", "Direct", 520_000, None, "n.lokuli@bcdc.cd"),
	("REGIDESO Equateur", "Guy", "Boyela", "Infrastructure", "Public tender", 2_100_000, 40, "g.boyela@regideso.cd"),
	("SNEL Direction Provinciale", "Fiston", "Engambe", "Infrastructure", "Public tender", 1_750_000, 45, "f.engambe@snel.cd"),
	("Hôtel Fleuve Congo Mbandaka", "Carine", "Nsimba", "Commercial", "Direct", 870_000, None, "c.nsimba@hotelfleuve.cd"),
	("Paroisse Sainte-Marie de Wangata", "Abbé Martin", "Ekofo", "Residential", "Referral", 180_000, None, "m.ekofo@paroisse-wangata.cd"),
	("Lycée Mama Mobutu", "Odette", "Bofala", "Education", "Public tender", 410_000, 28, "o.bofala@lycee-mm.cd"),
	("Office Congolais de Contrôle, Equateur", "Héritier", "Mpia", "Government", "Public tender", 760_000, 50, "h.mpia@occ.cd"),
	("Brasserie Bralima, dépôt Mbandaka", "Serge", "Kabila Nkoy", "Industrial", "Direct", 1_250_000, None, "s.nkoy@bralima.cd"),
	("Aéroport de Mbandaka (RVA)", "Patience", "Bokele", "Infrastructure", "Tender portal", 3_400_000, 60, "p.bokele@rva.cd"),
	("Cité des Fonctionnaires, phase 2", "Joël", "Likwela", "Residential", "Repeat client", 2_800_000, 35, "j.likwela@equateur.gouv.cd"),
	("Centre de Santé Bolenge", "Mireille", "Bokongo", "Healthcare", "Referral", 230_000, None, "m.bokongo@cs-bolenge.cd"),
	("Marché de Bakusu", "Albert", "Lifoli", "Commercial", "Public tender", 690_000, 21, "a.lifoli@mairie-mbandaka.cd"),
	("Tribunal de Grande Instance de Mbandaka", "Dieudonné", "Bosenge", "Government", "Public tender", 1_120_000, 42, "d.bosenge@justice.gouv.cd"),
]

# (party type, party, line 1, city, phone)
ADDRESSES = [
	("Customer", CUSTOMER, "Avenue du Gouverneur, Bâtiment administratif", "Mbandaka", "+243 81 400 1100"),
	("Supplier", "Kinshasa Building Supplies SARL", "12 Boulevard du 30 Juin, Gombe", "Kinshasa", "+243 81 500 2200"),
	("Supplier", "Congo Steel & Cement SARL", "Zone industrielle de Limete, 7e rue", "Kinshasa", "+243 82 300 4400"),
	("Supplier", "Matadi Clearing & Forwarding SARL", "Avenue du Port 3", "Matadi", "+243 85 120 3300"),
	("Supplier", "Fleuve Congo Barges SARL", "Beach Ngobila", "Kinshasa", "+243 89 700 5500"),
]

# (subject, priority, status, opened day, description)
ISSUES = [
	("Water ingress at annex B roof parapet", "High", "Open", -6,
	 "Rain on Monday came through the parapet capping above office B-12. Please inspect before the next storm."),
	("Door closer missing on fire door, level 1 east stair", "Medium", "Replied", -10,
	 "The FD60 door on the east stair does not self-close. Site team asked for the closer delivery date."),
	("Floor tile cracked in the main lobby", "Low", "Closed", -18,
	 "One 600x600 tile cracked near the reception desk; replaced from the attic stock on day -15."),
]

# (code, name, group, uom, rate)
TOOL_ITEMS = [
	("TLS-DRL-18V", "Cordless hammer drill 18 V", "Small Tools", "Nos", 240.0),
	("TLS-LVL-LSR", "Rotating laser level", "Small Tools", "Nos", 620.0),
	("TLS-GRD-230", "Angle grinder 230 mm", "Small Tools", "Nos", 135.0),
]
SPARE_ITEMS = [
	("EQ-SPR-HFLT", "Hydraulic return filter, 20 t excavator", "Heavy Equipment Items", "Nos", 85.0),
	("EQ-SPR-BKT", "Bucket tooth, 20 t excavator", "Heavy Equipment Items", "Nos", 42.0),
]
CENTRAL = "Central Store Kinshasa"
CUSTODY = "Tool Custody"


def run():
	open_leads()
	addresses()
	support_issues()
	small_tools()
	spare_parts()
	tool_issues()
	attic_stock_delivery()
	frappe.db.commit()


def open_leads():
	if frappe.db.exists("Lead", {"company_name": OPEN_LEADS[0][0]}):
		log("open leads already present")
		return
	for i, (org, first, last, sector, channel, value, due, email) in enumerate(OPEN_LEADS):
		with as_user("sales"):
			lead = insert({"doctype": "Lead", "first_name": first, "last_name": last, "company_name": org,
			               "email_id": email, "company": COMPANY, "territory": "All Territories",
			               "sector": sector, "enquiry_channel": channel, "estimated_value": value,
			               "project_location": "Mbandaka Site",
			               "tender_due_date": day(due) if due is not None else None, "lead_owner": user("sales")})
		frappe.db.set_value("Lead", lead.name, {"status": "Open", "creation": at(-20 + i, 9)}, update_modified=False)
	log(f"open leads: {len(OPEN_LEADS)}")


def addresses():
	for party_type, party, line1, city, phone in ADDRESSES:
		if not frappe.db.exists(party_type, party):
			continue
		if exists("Dynamic Link", {"link_doctype": party_type, "link_name": party, "parenttype": "Address"}):
			continue
		insert({"doctype": "Address", "address_title": party, "address_type": "Billing", "address_line1": line1,
		        "city": city, "country": "Congo, The Democratic Republic of the", "phone": phone,
		        "is_primary_address": 1, "links": [{"link_doctype": party_type, "link_name": party}]})
	if not exists("Dynamic Link", {"link_doctype": "Company", "link_name": COMPANY, "parenttype": "Address"}):
		insert({"doctype": "Address", "address_title": COMPANY, "address_type": "Office",
		        "address_line1": "45 Avenue Colonel Ebeya, Gombe", "city": "Kinshasa",
		        "country": "Congo, The Democratic Republic of the", "is_your_company_address": 1,
		        "links": [{"link_doctype": "Company", "link_name": COMPANY}]})
	log("addresses: the client, four suppliers and Masiha's office")


def support_issues():
	if exists("Issue", {"subject": ISSUES[0][0]}):
		log("support issues already present")
		return
	for priority in {row[1] for row in ISSUES}:
		if not frappe.db.exists("Issue Priority", priority):
			insert({"doctype": "Issue Priority", "name": priority, "__newname": priority})
	for subject, priority, status, opened, description in ISSUES:
		doc = insert({"doctype": "Issue", "subject": subject, "customer": CUSTOMER, "project": project(),
		              "company": COMPANY, "priority": priority, "raised_by": "facilities@equateur.gouv.cd",
		              "description": description, "opening_date": day(opened)})
		if status != "Open":
			frappe.db.set_value("Issue", doc.name, "status", status)
		frappe.db.set_value("Issue", doc.name, "creation", at(opened, 11), update_modified=False)
	log(f"support issues: {len(ISSUES)} (open, replied, closed)")


def small_tools():
	"""Tool and spare-part items, a custody store, and the tools' opening stock."""
	if not frappe.db.exists("Item Group", "Small Tools"):
		insert({"doctype": "Item Group", "item_group_name": "Small Tools", "parent_item_group": "All Item Groups"})
	for code, name, group, uom, rate in TOOL_ITEMS + SPARE_ITEMS:
		if not frappe.db.exists("Item", code):
			insert({"doctype": "Item", "item_code": code, "item_name": name, "item_group": group, "stock_uom": uom,
			        "is_stock_item": 1, "is_purchase_item": 1, "valuation_rate": rate,
			        "item_defaults": [{"company": COMPANY, "default_warehouse": wh(CENTRAL)}]})
	if not frappe.db.exists("Warehouse", wh(CUSTODY)):
		parent = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 1}, "name")
		insert({"doctype": "Warehouse", "warehouse_name": CUSTODY, "company": COMPANY, "parent_warehouse": parent})
	if exists("Stock Entry", {"company": COMPANY, "remarks": "Opening balance, small tools and spares", "docstatus": 1}):
		return
	insert({"doctype": "Stock Entry", "company": COMPANY, "stock_entry_type": "Material Receipt",
	        "posting_date": day(-60), "set_posting_time": 1, "remarks": "Opening balance, small tools and spares",
	        "items": [{"item_code": code, "qty": 10, "basic_rate": rate, "t_warehouse": wh(CENTRAL)}
	                  for code, _n, _g, _u, rate in TOOL_ITEMS + SPARE_ITEMS]},
	       submit=True)
	log("small tools and excavator spares in the central store, ten of each")


def spare_parts():
	if exists("Asset Spare Part", {"item_code": SPARE_ITEMS[0][0]}):
		log("spare parts already present")
		return
	asset = frappe.db.get_value("Asset", {"company": COMPANY, "item_code": "EQ-EXC-20T"}, "name")
	for code, _name, _group, _uom, _rate, part_no, minimum, reorder, note in (
		(*SPARE_ITEMS[0], "CAT-1R-0770", 2, 6, "Change every 500 operating hours."),
		(*SPARE_ITEMS[1], "CAT-1U3352", 4, 10, "Check wear weekly on rock excavation."),
	):
		insert({"doctype": "Asset Spare Part", "asset_category": "Heavy Equipment", "asset": asset,
		        "item_code": code, "part_no": part_no, "make": "CAT", "model": "320",
		        "min_stock_qty": minimum, "reorder_qty": reorder, "default_warehouse": wh(CENTRAL),
		        "default_supplier": "Equipements Lourds du Congo SARL", "remarks": note})
	log(f"spare parts listed against {asset}")


def tool_issues():
	if exists("Tool Issue", {"from_warehouse": wh(CENTRAL)}):
		log("tool issues already present")
		return
	for holder, code, qty, issued, due, label in (
		("requester", "TLS-DRL-18V", 2, -25, -5, "overdue"),
		("requester", "TLS-LVL-LSR", 1, -12, 20, "in date"),
		("operator", "TLS-GRD-230", 1, -8, 14, "in date"),
	):
		employee = (exists("Employee", {"user_id": user(holder), "company": COMPANY}) if holder != "operator"
		            else exists("Employee", {"first_name": "Joseph", "last_name": "Mbala", "company": COMPANY}))
		with as_user("stores"):
			doc = insert({"doctype": "Tool Issue", "issue_date": day(issued), "project": project(),
			              "site": "Mbandaka Site", "from_warehouse": wh(CENTRAL), "to_warehouse": wh(CUSTODY),
			              "issued_to": employee, "issued_by": user("stores"), "expected_return_date": day(due),
			              "items": [{"item_code": code, "qty": qty, "condition_on_issue": "Good",
			                         "expected_return_date": day(due)}]},
			             submit=True)
		log(f"tool issue {doc.name}: {qty} x {code} ({label})")


def attic_stock_delivery():
	"""Spare floor tiles handed to the client at handover, for future repairs."""
	if exists("Delivery Note", {"company": COMPANY, "customer": CUSTOMER}):
		log("attic stock delivery already present")
		return
	code, qty = "FIN-POR-600", 20
	# Bought for the job, never sold until now: the handover is the first sale of it.
	frappe.db.set_value("Item", code, "is_sales_item", 1)
	store = frappe.db.get_value("Bin", {"item_code": code, "warehouse": ["like", f"% - {frappe.db.get_value('Company', COMPANY, 'abbr')}"],
	                                     "actual_qty": [">=", qty]}, "warehouse", order_by="actual_qty desc")
	doc = frappe.get_doc({"doctype": "Delivery Note", "company": COMPANY, "customer": CUSTOMER, "currency": "USD",
	                      "posting_date": day(-3), "set_posting_time": 1, "project": project(),
	                      "instructions": "Attic stock: spare tiles for the client's maintenance team.",
	                      "items": [{"item_code": code, "qty": qty, "rate": 23.0,
	                                 "warehouse": store or wh("Mbandaka Site Store")}]})
	doc.flags.ignore_permissions = True
	doc.insert()
	if store:
		doc.submit()
		log(f"delivery note {doc.name}: {qty} m2 of attic stock from {store}")
	else:
		log(f"delivery note {doc.name} left as a draft: no store holds {qty} m2 of {code}")
