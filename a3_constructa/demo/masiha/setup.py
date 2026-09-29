# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Step 1, the controls: the company, its people, and how approvals work.

Everything here is configuration a real implementation would also need, which
is why it is built the standard way (workflows, user permissions, price lists)
rather than coded: the demo can say "this is configuration, not customization".
"""

import frappe
from frappe.utils import flt

from a3_constructa.demo.masiha.common import (
	ABBR,
	BUYING_PRICE_LIST,
	COMPANY,
	COUNTRY,
	CURRENCY,
	DEMO_PASSWORD,
	PEOPLE,
	SELLING_PRICE_LIST,
	acc,
	day,
	exists,
	insert,
	log,
	user,
)


def run():
	install_app_custom_fields()
	create_company()
	make_default()
	create_price_lists_and_rates()
	create_uoms()
	create_accounts()
	create_payment_terms()
	create_tax_templates()
	create_users()
	create_employees()
	create_asset_category()
	add_cash_purchase_series()
	create_dispatch_entry_type()
	create_workflows()
	frappe.db.commit()


def install_app_custom_fields():
	"""The app's own custom fields that this site has not had a migrate for yet."""
	import json

	path = frappe.get_app_path("a3_constructa", "fixtures", "custom_field.json")
	for entry in json.load(open(path)):
		if not frappe.db.exists("Custom Field", entry["name"]):
			frappe.get_doc(entry).insert(ignore_permissions=True)


def create_company():
	if frappe.db.exists("Company", COMPANY):
		log("company already present")
		return
	insert({
		"doctype": "Company",
		"company_name": COMPANY,
		"abbr": ABBR,
		"default_currency": CURRENCY,
		"country": COUNTRY,
		"create_chart_of_accounts_based_on": "Standard Template",
		"chart_of_accounts": "Standard",
		"enable_perpetual_inventory": 1,
	})
	log(f"company {COMPANY} ({CURRENCY}, {COUNTRY})")


def make_default():
	"""The demo company is the site's default, so every screen opens on it."""
	frappe.db.set_single_value("Global Defaults", "default_company", COMPANY)
	frappe.db.set_single_value("Global Defaults", "default_currency", CURRENCY)
	frappe.db.set_default("company", COMPANY)
	frappe.db.set_default("currency", CURRENCY)
	# The installation came from an India setup; this client reads 1,157,310, not 11,57,310.
	# Saved through the document so the site default the screens read is updated too.
	settings = frappe.get_single("System Settings")
	settings.number_format = "#,###.##"
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.set_default("number_format", "#,###.##")
	frappe.cache.delete_key("bootinfo")
	frappe.defaults.set_user_default("Company", COMPANY, "Administrator")
	log("default company set")


def create_price_lists_and_rates():
	for name, buying, selling in ((BUYING_PRICE_LIST, 1, 0), (SELLING_PRICE_LIST, 0, 1)):
		if not frappe.db.exists("Price List", name):
			insert({"doctype": "Price List", "price_list_name": name, "currency": CURRENCY,
			        "buying": buying, "selling": selling, "enabled": 1})
	frappe.db.set_single_value("Buying Settings", "buying_price_list", BUYING_PRICE_LIST)
	# Step 20: suppliers are paid for what was accepted, not for what was rejected at the GRN.
	frappe.db.set_single_value("Buying Settings", "bill_for_rejected_quantity_in_purchase_invoice", 0)
	frappe.db.set_single_value("Selling Settings", "selling_price_list", SELLING_PRICE_LIST)

	# The site has no internet to fetch rates, so the ones the story uses are
	# recorded, as a treasury would record them.
	for source, target, rate in (("EUR", "USD", 1.08), ("USD", "EUR", 0.926), ("CNY", "USD", 0.139),
	                             ("INR", "USD", 0.012), ("USD", "INR", 83.2), ("USD", "CDF", 2850.0),
	                             ("CDF", "USD", 0.000351)):
		for currency in (source, target):
			if not frappe.db.exists("Currency", currency):
				continue
			frappe.db.set_value("Currency", currency, "enabled", 1)
		if not exists("Currency Exchange", {"from_currency": source, "to_currency": target}):
			insert({"doctype": "Currency Exchange", "date": day(-170), "from_currency": source,
			        "to_currency": target, "exchange_rate": rate, "for_buying": 1, "for_selling": 1})
	log("USD price lists; EUR, CNY and INR exchange rates")


def create_uoms():
	for name, whole in (("Bag", 1), ("Lump Sum", 1)):
		if not frappe.db.exists("UOM", name):
			insert({"doctype": "UOM", "uom_name": name, "must_be_whole_number": whole})


def create_accounts():
	"""A USD bank account and an input VAT account, beside the standard chart."""
	for name, parent, account_type in (
		("Rawbank USD", "Bank Accounts", "Bank"),
		("VAT Input 16%", "Duties and Taxes", "Tax"),
		("VAT Output 16%", "Duties and Taxes", "Tax"),
		("Import Freight and Clearing", "Direct Expenses", "Expenses Included In Valuation"),
	):
		if frappe.db.exists("Account", acc(name)):
			continue
		insert({"doctype": "Account", "account_name": name, "company": COMPANY,
		        "parent_account": acc(parent), "account_type": account_type})
	frappe.db.set_value("Company", COMPANY, "default_bank_account", acc("Rawbank USD"))
	for mode, account in (("Wire Transfer", "Rawbank USD"), ("Cash", "Cash")):
		mop = frappe.get_doc("Mode of Payment", mode)
		if not any(row.company == COMPANY for row in mop.accounts):
			mop.append("accounts", {"company": COMPANY, "default_account": acc(account)})
			mop.save(ignore_permissions=True)
	log("bank, VAT and freight accounts")


def create_payment_terms():
	for term, portion, based_on, days in (
		("30% Advance", 30, "Day(s) after invoice date", 0),
		("70% on Delivery", 70, "Day(s) after invoice date", 30),
		("Net 30", 100, "Day(s) after invoice date", 30),
	):
		if not frappe.db.exists("Payment Term", term):
			insert({"doctype": "Payment Term", "payment_term_name": term, "invoice_portion": portion,
			        "due_date_based_on": based_on, "credit_days": days})
	for template, terms in (("30% Advance, 70% on Delivery", ["30% Advance", "70% on Delivery"]),
	                        ("Net 30 Days", ["Net 30"])):
		if frappe.db.exists("Payment Terms Template", template):
			continue
		insert({"doctype": "Payment Terms Template", "template_name": template, "terms": [
			{"payment_term": term, "invoice_portion": frappe.db.get_value("Payment Term", term, "invoice_portion"),
			 "due_date_based_on": "Day(s) after invoice date",
			 "credit_days": frappe.db.get_value("Payment Term", term, "credit_days")} for term in terms]})
	log("payment terms: 30/70 and net 30")


def create_tax_templates():
	title = "DRC VAT 16%"
	if not exists("Purchase Taxes and Charges Template", {"title": title, "company": COMPANY}):
		insert({"doctype": "Purchase Taxes and Charges Template", "title": title, "company": COMPANY,
		        "taxes": [{"charge_type": "On Net Total", "account_head": acc("VAT Input 16%"), "rate": 16,
		                   "description": "VAT 16%", "category": "Total", "add_deduct_tax": "Add"}]})
	if not exists("Sales Taxes and Charges Template", {"title": title, "company": COMPANY}):
		insert({"doctype": "Sales Taxes and Charges Template", "title": title, "company": COMPANY,
		        "taxes": [{"charge_type": "On Net Total", "account_head": acc("VAT Output 16%"), "rate": 16,
		                   "description": "VAT 16%"}]})
	log("VAT 16% purchase and sales templates")


def create_users():
	for key, (first, last, _title, roles) in PEOPLE.items():
		email = user(key)
		if not frappe.db.exists("User", email):
			doc = frappe.get_doc({"doctype": "User", "email": email, "first_name": first, "last_name": last,
			                      "send_welcome_email": 0, "user_type": "System User", "new_password": DEMO_PASSWORD,
			                      "roles": [{"role": role} for role in roles]})
			doc.flags.ignore_permissions = True
			doc.flags.no_welcome_mail = True
			doc.insert()
		else:
			doc = frappe.get_doc("User", email)
			missing = set(roles) - {row.role for row in doc.roles}
			if missing:
				doc.add_roles(*missing)
		# Each demo user sees the demo company only; the other companies' records
		# stay out of their lists, and it becomes their default company.
		if not exists("User Permission", {"user": email, "allow": "Company", "for_value": COMPANY}):
			insert({"doctype": "User Permission", "user": email, "allow": "Company", "for_value": COMPANY,
			        "is_default": 1, "apply_to_all_doctypes": 1})
	log(f"{len(PEOPLE)} demo users, password '{DEMO_PASSWORD}', limited to {COMPANY}")


def create_employees():
	people = [(key, *PEOPLE[key][:3]) for key in PEOPLE] + [("operator", "Joseph", "Mbala", "Plant Operator")]
	for key, first, last, _title in people:
		if exists("Employee", {"first_name": first, "last_name": last, "company": COMPANY}):
			continue
		insert({"doctype": "Employee", "first_name": first, "last_name": last, "company": COMPANY,
		        "gender": "Female" if first in ("Chantal", "Esther", "Marie", "Grace") else "Male",
		        "date_of_birth": "1986-05-14", "date_of_joining": "2021-02-01", "status": "Active",
		        "user_id": user(key) if key in PEOPLE else None})
	log("employees for every person in the story, plus a plant operator")


def create_asset_category():
	name = "Heavy Equipment"
	accounts = {"company_name": COMPANY, "fixed_asset_account": acc("Plants and Machineries"),
	            "accumulated_depreciation_account": acc("Accumulated Depreciation"),
	            "depreciation_expense_account": acc("Depreciation")}
	if not frappe.db.exists("Asset Category", name):
		insert({"doctype": "Asset Category", "asset_category_name": name, "enable_cwip_accounting": 0,
		        "asset_naming_series": "HEQ-.####",
		        "finance_books": [{"depreciation_method": "Straight Line", "total_number_of_depreciations": 60,
		                           "frequency_of_depreciation": 1}], "accounts": [accounts]})
	doc = frappe.get_doc("Asset Category", name)
	if not any(row.company_name == COMPANY for row in doc.accounts):
		doc.append("accounts", accounts)
		doc.save(ignore_permissions=True)
	log("asset category Heavy Equipment, numbered HEQ-")


def add_cash_purchase_series():
	"""Step 15: a regularization PO for a cash purchase is numbered PUR-CASH-."""
	options = frappe.get_meta("Purchase Order").get_field("naming_series").options or ""
	if "PUR-CASH-" not in options:
		frappe.make_property_setter({"doctype": "Purchase Order", "fieldname": "naming_series",
		                             "property": "options", "value": options.strip() + "\nPUR-CASH-.YYYY.-",
		                             "property_type": "Text"})
	log("cash-purchase PO series PUR-CASH-")


def create_dispatch_entry_type():
	"""Step 16, the client's MIN: stock leaving the central store for site.

	It moves into the transit warehouse and stays visible there until the site
	receives it against this entry (the MRN). The app's own "Material Issue Note
	(MIN)" is consumption on site, step 18.
	"""
	if not frappe.db.exists("Stock Entry Type", "Warehouse Dispatch (MIN)"):
		insert({"doctype": "Stock Entry Type", "__newname": "Warehouse Dispatch (MIN)",
		        "purpose": "Material Transfer", "add_to_transit": 1})
	log("stock entry type: Warehouse Dispatch (MIN), into transit")


# ------------------------------------------------------------------ workflows
# Steps 6 and 8: requests are verified by stores and approved by the project
# manager, and purchase orders are approved before they are released.
PR_WORKFLOW = "Masiha PR Approval"
PO_WORKFLOW = "Masiha PO Approval"


def create_workflows():
	for state, style in (("Stores Verification", "Warning"), ("Released to Supplier", "Success"),
	                     ("Draft", ""), ("Pending Approval", "Warning")):
		if not frappe.db.exists("Workflow State", state):
			insert({"doctype": "Workflow State", "workflow_state_name": state, "style": style})
	for action in ("Submit for Verification", "Verify Stock", "Return for Correction", "Approve", "Reject",
	               "Submit for Approval", "Release to Supplier"):
		if not frappe.db.exists("Workflow Action Master", action):
			insert({"doctype": "Workflow Action Master", "workflow_action_name": action})

	if not frappe.db.exists("Workflow", PR_WORKFLOW):
		insert({
			"doctype": "Workflow", "workflow_name": PR_WORKFLOW, "document_type": "Material Request",
			"workflow_state_field": "workflow_state", "is_active": 1, "send_email_alert": 0,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": "Stock User"},
				{"state": "Stores Verification", "doc_status": "0", "allow_edit": "Constructa Store Keeper"},
				{"state": "Pending Approval", "doc_status": "0", "allow_edit": "Constructa Project Manager"},
				{"state": "Approved", "doc_status": "1", "allow_edit": "Purchase User"},
				{"state": "Rejected", "doc_status": "0", "allow_edit": "Constructa Project Manager"},
			],
			"transitions": [
				{"state": "Draft", "action": "Submit for Verification", "next_state": "Stores Verification",
				 "allowed": "Stock User", "allow_self_approval": 1},
				{"state": "Stores Verification", "action": "Verify Stock", "next_state": "Pending Approval",
				 "allowed": "Constructa Store Keeper", "allow_self_approval": 1},
				{"state": "Stores Verification", "action": "Return for Correction", "next_state": "Draft",
				 "allowed": "Constructa Store Keeper", "allow_self_approval": 1},
				{"state": "Pending Approval", "action": "Approve", "next_state": "Approved",
				 "allowed": "Constructa Project Manager", "allow_self_approval": 1},
				{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected",
				 "allowed": "Constructa Project Manager", "allow_self_approval": 1},
				{"state": "Pending Approval", "action": "Return for Correction", "next_state": "Draft",
				 "allowed": "Constructa Project Manager", "allow_self_approval": 1},
			],
		})
	if not frappe.db.exists("Workflow", PO_WORKFLOW):
		insert({
			"doctype": "Workflow", "workflow_name": PO_WORKFLOW, "document_type": "Purchase Order",
			"workflow_state_field": "workflow_state", "is_active": 1, "send_email_alert": 0,
			"states": [
				{"state": "Draft", "doc_status": "0", "allow_edit": "Purchase User"},
				{"state": "Pending Approval", "doc_status": "0", "allow_edit": "Purchase Manager"},
				{"state": "Approved", "doc_status": "1", "allow_edit": "Purchase Manager"},
				{"state": "Released to Supplier", "doc_status": "1", "allow_edit": "Purchase User"},
				{"state": "Rejected", "doc_status": "0", "allow_edit": "Purchase Manager"},
			],
			"transitions": [
				{"state": "Draft", "action": "Submit for Approval", "next_state": "Pending Approval",
				 "allowed": "Purchase User", "allow_self_approval": 1},
				{"state": "Pending Approval", "action": "Approve", "next_state": "Approved",
				 "allowed": "Purchase Manager", "allow_self_approval": 1},
				{"state": "Pending Approval", "action": "Reject", "next_state": "Rejected",
				 "allowed": "Purchase Manager", "allow_self_approval": 1},
				{"state": "Approved", "action": "Release to Supplier", "next_state": "Released to Supplier",
				 "allowed": "Purchase User", "allow_self_approval": 1},
			],
		})
	log("workflows: PR verify/approve/reject/return; PO approve then release")
