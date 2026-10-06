# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02A: the tenders Masiha is chasing in Equateur province.

Six leads, from a fresh enquiry to one that went quiet, and seven opportunities
across the sales stages: three converted from leads (the five construction
fields carried across), four with the provincial government as a repeat
client, one of them lost and one closed. Two tenders fall due this week: the
hospital extension has no quotation yet (it shows under "Due soon"), the
university library has one.
"""

import frappe
from erpnext.crm.doctype.lead.lead import make_opportunity
from frappe.utils import add_days

from a3_constructa.demo.masiha.common import COMPANY, CUSTOMER, as_user, at, comment, day, insert, log, user

# (key, organisation, contact first, last, sector, channel, value, tender due, lead status, opportunity)
# opportunity: None, or (title, stage, probability, award day, duration months, site visit day)
LEADS = [
	("hospital", "Hôpital Général de Référence de Mbandaka", "Jean-Pierre", "Bolamba", "Healthcare", "Public tender",
	 2_400_000, 5, None, ("Hospital extension: maternity and theatre block", "Proposal/Price Quote", 40, 45, 18, -12)),
	("university", "Université de Mbandaka", "Clarisse", "Ikoli", "Education", "Tender portal",
	 1_150_000, 6, None, ("University library block", "Proposal/Price Quote", 50, 40, 12, -15)),
	("road", "Office des Routes, Equateur", "Rigobert", "Mbuyi", "Infrastructure", "Public tender",
	 6_500_000, 30, None, ("Route Mbandaka-Bikoro rehabilitation, lot 2", "Qualification", 20, 120, 24, None)),
	("port", "Port de Mbandaka (SCTP)", "Alphonse", "Ekila", "Industrial", "Referral",
	 900_000, None, "Replied", None),
	("residence", "Résidence du Gouverneur", "Sylvie", "Bokungu", "Residential", "Direct",
	 350_000, None, "Interested", None),
	("market", "Marché central de Mbandaka", "Didier", "Lisanga", "Commercial", "Direct",
	 1_800_000, None, "Lead", None),
]

# Repeat client: (title, sector, value, stage, probability, award day, tender due day, status, note)
CLIENT = [
	("Administrative Centre: annex B offices", "Government", 3_200_000, "Negotiation/Review", 70, 20, -10, "Replied",
	 "Bid submitted; client asked for a 4% discount on the finishes."),
	("Provincial Assembly: roof replacement", "Government", 420_000, "Proposal/Price Quote", 30, -20, -45, "Lost",
	 "Lost on price to a Kinshasa contractor."),
	("Stade de Mbandaka: stand repairs", "Government", 760_000, "Prospecting", 10, 60, None, "Closed",
	 "Client withdrew the tender: no budget this year."),
	("Water tower, Wangata commune", "Infrastructure", 1_300_000, "Needs Analysis", 25, 90, 21, "Open",
	 "Site visit planned with REGIDESO."),
]


def run():
	if frappe.db.exists("Lead", {"company_name": LEADS[0][1]}):
		log("CRM pipeline already present")
		return
	from a3_constructa.demo.masiha.setup import create_employees, create_users

	create_users()  # Bernadette Mbo, business development, joined the cast in P-02A
	create_employees()
	ensure_lost_reason()
	made = [create_lead(*row) for row in LEADS]
	made += [create_client_opportunity(*row) for row in CLIENT]
	quote_university()
	log("CRM: " + ", ".join(made))


def ensure_lost_reason():
	if not frappe.db.exists("Opportunity Lost Reason", "Price"):
		insert({"doctype": "Opportunity Lost Reason", "lost_reason": "Price"})


def create_lead(key, org, first, last, sector, channel, value, due, status, opp):
	with as_user("sales"):
		lead = insert({"doctype": "Lead", "first_name": first, "last_name": last, "company_name": org, "company": COMPANY,
		               "source": "Advertisement" if channel == "Public tender" else None, "territory": "All Territories",
		               "sector": sector, "enquiry_channel": channel, "estimated_value": value,
		               "project_location": "Mbandaka Site" if key != "road" else None,
		               "tender_due_date": day(due) if due is not None else None, "lead_owner": user("sales")})
	frappe.db.set_value("Lead", lead.name, "creation", at(-40, 9), update_modified=False)
	if status:
		frappe.db.set_value("Lead", lead.name, "status", status)
	if not opp:
		return f"{lead.name} ({status or 'Lead'})"

	title, stage, probability, award, months, visit = opp
	with as_user("sales"):
		o = make_opportunity(lead.name)  # carries sector, location, value, channel and due date across
		o.update({"title": title, "company": COMPANY, "currency": "USD", "sales_stage": stage, "probability": probability,
		          "opportunity_amount": value if key != "road" else 0, "expected_closing": day(award),
		          "expected_award_date": day(award), "estimated_duration_months": months,
		          "site_visit_date": day(visit) if visit is not None else None, "opportunity_owner": user("sales"),
		          "transaction_date": day(-30)})
		o.flags.ignore_permissions = True
		o.insert()
	frappe.db.set_value("Opportunity", o.name, "creation", at(-30, 10), update_modified=False)
	if visit is not None:
		comment("Opportunity", o.name, "Site visit done: access by river, materials to come by barge from Kinshasa.", "qs", at(visit, 16))
	return f"{lead.name} -> {o.name}"


def create_client_opportunity(title, sector, value, stage, probability, award, due, status, note):
	with as_user("sales"):
		o = insert({"doctype": "Opportunity", "opportunity_from": "Customer", "party_name": CUSTOMER, "company": COMPANY,
		            "title": title, "currency": "USD", "opportunity_amount": value, "sales_stage": stage,
		            "probability": probability, "expected_closing": day(award), "expected_award_date": day(award),
		            "sector": sector, "enquiry_channel": "Repeat client", "estimated_value": value,
		            "project_location": "Mbandaka Site", "tender_due_date": day(due) if due is not None else None,
		            "opportunity_owner": user("qs"), "transaction_date": day(-50)})
	frappe.db.set_value("Opportunity", o.name, "creation", at(-50, 10), update_modified=False)
	if status == "Lost":
		o.reload()
		o.declare_enquiry_lost([{"lost_reason": "Price"}], [], note)
	elif status in ("Replied", "Closed"):
		frappe.db.set_value("Opportunity", o.name, "status", status)
	comment("Opportunity", o.name, note, "sales", at(-5, 11))
	return f"{o.name} ({status})"


def quote_university():
	"""The library tender, due this week, already has a draft quotation."""
	opp = frappe.db.get_value("Opportunity", {"title": "University library block"}, "name")
	if not opp or frappe.db.exists("Quotation", {"opportunity": opp}):
		return
	from erpnext.crm.doctype.opportunity.opportunity import make_quotation

	q = make_quotation(opp)
	q.company = COMPANY
	q.transaction_date = day(-2)
	q.valid_till = add_days(day(-2), 30)
	q.append("items", {"item_code": "CW-ARCH", "qty": 1, "rate": 1_150_000,
	                   "description": "Library block, design and build, lump sum (draft for review)"})
	q.flags.ignore_permissions = True
	with as_user("sales"):
		q.insert()
