# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02E: quotations, their revisions, margin approval and how they ended.

- The hospital tender is quoted from its BOQ at a 14.7% margin and sent. The
  client caps its budget at $530,000, so the QS cuts profit and risk on the
  BOQ, sales re-issues the quotation as revision 1 at 9.5%, below the 10%
  minimum, and the managing director approves it.
- Three earlier bids for the provincial government and the port give the
  win / loss reports something to show: the Administrative Centre (won, now
  award AQ-2026-0001), annex B (open, revised for a 4% discount), and two
  lost on price, with the competitor and the price that won.
"""

import frappe
from frappe.utils import add_days

from a3_constructa.demo.masiha.common import (
	COMPANY, CUSTOMER, as_user, at, comment, day, insert, log, transition, user,
)

HOSPITAL = "Hospital extension: maternity and theatre block"
LOST_REASONS = ("Price", "Programme too long", "Technical score")
COMPETITORS = ("Kin Bâtisseurs SARL", "Sino-Congo Construction")
SERVICE_ITEM = "CW-ARCH"


def run():
	if frappe.db.exists("Quotation", {"boq": ["is", "set"], "company": COMPANY}):
		log("quotations already present")
		return
	from a3_constructa.demo.masiha.setup import create_employees, create_users

	create_users()  # Albert Nzuzi, managing director, joined the cast in P-02E
	create_employees()
	for reason in LOST_REASONS:
		if not frappe.db.exists("Quotation Lost Reason", reason):
			insert({"doctype": "Quotation Lost Reason", "order_lost_reason": reason})
	for name in COMPETITORS:
		if not frappe.db.exists("Competitor", name):
			insert({"doctype": "Competitor", "competitor_name": name})

	made = [won_admin_centre(), annex_b(), lost_assembly_roof(), lost_port()]
	made.append(hospital())
	log("Quotations: " + "; ".join(m for m in made if m))


# ---------------------------------------------------------------- history

def lump_sum(party_type, party, title_line, value, on, opportunity=None, valid_days=30):
	"""A one-line lump-sum bid, as sales sends it, dated on the story day."""
	with as_user("sales"):
		q = frappe.new_doc("Quotation")
		q.update({"quotation_to": party_type, "party_name": party, "company": COMPANY, "currency": "USD",
		          "transaction_date": day(on), "valid_till": day(on + valid_days), "order_type": "Sales",
		          "opportunity": opportunity})
		q.append("items", {"item_code": SERVICE_ITEM, "qty": 1, "rate": value, "description": title_line})
		q.flags.ignore_permissions = True
		q.insert()
	frappe.db.set_value("Quotation", q.name, {"creation": at(on, 9), "modified": at(on, 9)}, update_modified=False)
	return transition("Quotation", q.name, "Submit", "sales", at(on, 15))


def won_admin_centre():
	"""The bid behind the live project: award AQ-2026-0001 names it."""
	award = frappe.db.get_value("Awarded Quotation", {"company": COMPANY, "quotation": ["is", "not set"]},
	                            ["name", "award_date", "contract_value", "title"], as_dict=True, order_by="creation asc")
	if not award:
		return None
	on = (frappe.utils.getdate(award.award_date) - frappe.utils.getdate(day(0))).days - 40
	opp = insert({"doctype": "Opportunity", "opportunity_from": "Customer", "party_name": CUSTOMER, "company": COMPANY,
	              "title": "Mbandaka Administrative Centre: design and build", "currency": "USD", "sector": "Government",
	              "opportunity_amount": award.contract_value, "estimated_value": award.contract_value,
	              "sales_stage": "Negotiation/Review", "probability": 100, "transaction_date": day(on - 30),
	              "expected_closing": award.award_date, "opportunity_owner": user("sales")})
	q = lump_sum("Customer", CUSTOMER, "Administrative Centre, design and build, lump sum", award.contract_value, on, opp.name)
	frappe.db.set_value("Awarded Quotation", award.name, "quotation", q.name)
	frappe.db.set_value("Opportunity", opp.name, "status", "Converted")
	comment("Quotation", q.name, f"Awarded: {award.name}, signed on {frappe.utils.formatdate(award.award_date)}.", "sales",
	        at((frappe.utils.getdate(award.award_date) - frappe.utils.getdate(day(0))).days, 16))
	return f"{q.name} won ({award.name})"


def annex_b():
	"""Annex B offices: bid sent, then re-issued with the 4% discount the client asked for."""
	opp = frappe.db.get_value("Opportunity", {"title": "Administrative Centre: annex B offices"}, "name")
	if not opp:
		return None
	q = lump_sum("Customer", CUSTOMER, "Annex B offices, design and build, lump sum", 3_150_000, -24, opp)
	revised = amend(q.name, "Client asked for a 4% discount on the finishes; finishes package re-tendered.", -12)
	revised.items[0].rate = 3_150_000 - 0.04 * 1_150_000  # 4% off the $1.15M finishes package
	with as_user("sales"):
		revised.save(ignore_permissions=True)
	transition("Quotation", revised.name, "Submit", "sales", at(-12, 15))
	return f"{q.name} → {revised.name} (open)"


def lost_assembly_roof():
	opp = frappe.db.get_value("Opportunity", {"title": "Provincial Assembly: roof replacement"}, "name")
	if not opp:
		return None
	q = lump_sum("Customer", CUSTOMER, "Assembly roof replacement, lump sum", 412_000, -50, opp)
	lose(q.name, ["Price"], ["Kin Bâtisseurs SARL"], 371_000,
	     "Kinshasa contractor 10% under us; they bring their own roofing crew.", -22)
	return f"{q.name} lost on price"


def lost_port():
	lead = frappe.db.get_value("Lead", {"company_name": "Port de Mbandaka (SCTP)"}, "name")
	if not lead:
		return None
	q = lump_sum("Lead", lead, "Port warehouse extension, design and build, lump sum", 905_000, -35)
	lose(q.name, ["Programme too long", "Price"], ["Sino-Congo Construction"], 840_000,
	     "Client needed the warehouse before the rainy season: our 9-month programme lost to a 6-month one.", -8)
	return f"{q.name} lost on programme"


def amend(name, reason, on, by="sales"):
	with as_user(by):
		frappe.get_doc("Quotation", name).cancel()
		old = frappe.get_doc("Quotation", name)
		new = frappe.copy_doc(old, ignore_no_copy=False)
		new.update({"amended_from": name, "revision_reason": reason, "transaction_date": day(on), "valid_till": day(on + 30)})
		new.flags.ignore_permissions = True
		new.insert()
	frappe.db.set_value("Quotation", new.name, {"creation": at(on, 9), "modified": at(on, 9)}, update_modified=False)
	return frappe.get_doc("Quotation", new.name)


def lose(name, reasons, competitors, price, note, on):
	from a3_constructa.overrides.quotation import declare_lost

	with as_user("sales"):
		declare_lost(name, [{"lost_reason": r} for r in reasons], [{"competitor": c} for c in competitors], note, price)
	frappe.db.set_value("Quotation", name, "modified", at(on, 11), update_modified=False)
	comment("Quotation", name, f"Lost: {', '.join(reasons).lower()}. {note}", "sales", at(on, 11))


# ---------------------------------------------------------------- the hospital tender

def hospital():
	from a3_constructa.overrides.quotation import make_from_boq, update_from_boq

	opp = frappe.db.get_value("Opportunity", {"title": HOSPITAL}, "name")
	boq = frappe.db.get_value("BOQ", {"opportunity": opp, "boq_stage": "Tender"}, "name") if opp else None
	if not boq or not frappe.db.get_value("BOQ", boq, "profit_percent"):
		log("hospital tender not priced; run the pricing stage first")
		return None

	# The QS, who reads the BOQ, makes the quotation from it; sales sends it.
	with as_user("qs"):
		first = make_from_boq(boq)["name"]
		q = frappe.get_doc("Quotation", first)
		q.exclusions = "\n".join([
			"Medical equipment and furniture (by the client)",
			"Connection fees to the SNEL grid and REGIDESO water main",
			"Removal of contaminated soil, if found",
			"VAT, which is added at the rate in force",
		])
		q.save(ignore_permissions=True)
	transition("Quotation", first, "Submit", "sales", at(0, 9, 30),
	           f"Sent to the client with the tender: {q.margin_percent:.1f}% margin.")

	# The client's budget is capped: the QS takes profit to 2% and risk to 1% on the BOQ.
	with as_user("qs"):
		b = frappe.get_doc("BOQ", boq)
		b.update({"profit_percent": 2, "risk_percent": 1})
		b.flags.ignore_permissions = True
		b.save()
	comment("BOQ", boq, "Client caps the budget at $530,000: profit 7% → 2%, risk 3% → 1%. Overhead unchanged.", "qs", at(0, 11))

	revised = amend(first, "Client's budget is capped at $530,000: profit cut to 2% and risk to 1% on the BOQ.", 0, "qs")
	with as_user("qs"):
		update_from_boq(revised.name)
	transition("Quotation", revised.name, "Submit for Approval", "sales", at(0, 12),
	           "Margin now 9.5%, under our 10% floor. Asking Albert to approve: it keeps us in the race.")
	transition("Quotation", revised.name, "Approve", "md", at(0, 14),
	           "Approved at 9.5%. A strategic job for the healthcare sector; hold the overhead.")
	final = frappe.get_doc("Quotation", revised.name)
	return f"{first} → {revised.name}: ${final.grand_total:,.2f}, margin {final.margin_percent:.1f}%, {final.workflow_state}"
