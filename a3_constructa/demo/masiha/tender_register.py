# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02G: tender documents and clarifications.

- University library (due in 4 days): instructions to tenderers, drawings rev A
  then rev B (A superseded), specification, the client's BOQ (the CSV already
  on the opportunity) and Addendum 1. Three queries: floor loading (answered, no
  price impact), sprinklers (answered by Addendum 1, a $38,000 provisional sum:
  price impact), the missing soil report (open 6 days).
- Wangata water tower: specification and drawings; tank capacity, 500 or
  600 m³? (open 2 days).
- Wangata solar retrofit: battery autonomy (answered: smaller bank, price impact).
- Hospital extension (won): its tender documents and a medical gas query,
  answered with a price impact, kept as history.
"""

import frappe

from a3_constructa.demo.masiha.common import as_user, at, day, log

LIBRARY, WATER = "University library block", "Water tower, Wangata commune"
SOLAR, HOSPITAL = "Wangata health centre: solar power retrofit", "Hospital extension: maternity and theatre block"

# tender -> [(document type, title, revision, received days ago, attachment from the opportunity's files)]
DOCUMENTS = {
	LIBRARY: [
		("Invitation to Tender", "Instructions to tenderers and form of tender", "0", -38, False),
		("Tender Drawings", "Architectural and structural drawings", "A", -38, False),
		("Specification", "Technical specification", "0", -38, False),
		("Bill of Quantities", "Bill of quantities", "0", -38, True),
		("Tender Drawings", "Architectural and structural drawings", "B", -20, False),
		("Tender Addendum", "Addendum 1: sprinklers to the reading rooms", "1", -9, False),
	],
	WATER: [
		("Specification", "Water tower specification", "0", -10, False),
		("Tender Drawings", "Tower and tank drawings", "0", -10, False),
	],
	SOLAR: [
		("Invitation to Tender", "Request for proposals, solar retrofit", "0", -12, False),
		("Specification", "Solar and battery specification", "0", -12, False),
	],
	HOSPITAL: [
		("Invitation to Tender", "Instructions to tenderers", "0", -75, False),
		("Bill of Quantities", "Bill of quantities", "0", -75, False),
		("Tender Drawings", "Maternity and theatre block drawings", "C", -60, False),
	],
}
# tender -> [(question, raised days ago, answer, answered days ago, price impact note)]
QUERIES = {
	LIBRARY: [
		("Is the floor loading of 7.5 kN/m² in the stack areas for us to design?", -30,
		 "No: the structural engineer's design governs. Price to the drawings.", -26, None),
		("Drawing rev B shows sprinkler heads in the reading rooms but the BOQ has no sprinkler items. Please confirm the scope.", -18,
		 "Sprinklers are in scope: see Addendum 1, with a provisional sum of $38,000.", -9,
		 "Add the $38,000 provisional sum for sprinklers to the tender BOQ."),
		("The soil investigation report in specification clause 2.3 was not issued. Please provide it or confirm the allowable bearing pressure.",
		 -6, None, None, None),
	],
	WATER: [
		("Tank capacity: drawing T-02 shows 500 m³, the specification 600 m³. Which applies?", -2, None, None, None),
	],
	SOLAR: [
		("Battery autonomy of 8 hours: for the theatre and maternity wards only, or the whole centre?", -9,
		 "Theatre and maternity wards only; the rest of the centre runs on daytime solar.", -5,
		 "Smaller battery bank: about 40 kWh instead of 120 kWh."),
	],
	HOSPITAL: [
		("How many medical gas outlets per operating theatre?", -70,
		 "Six per theatre: oxygen, medical air and two vacuum, plus two nitrous oxide.", -66,
		 "Medical gas outlets priced at 6 per theatre (BOQ C/03/01)."),
	],
}


def run():
	made = []
	for title in DOCUMENTS:
		name = frappe.db.get_value("Opportunity", {"title": title}, "name")
		if not name:
			continue
		made.append(f"{name}: {documents(name, title)} documents, {queries(name, title)} queries")
	log("Tender register: " + "; ".join(made))


def documents(name, title):
	o = frappe.get_doc("Opportunity", name)
	if o.get("tender_documents"):
		return 0
	files = frappe.get_all("File", filters={"attached_to_doctype": "Opportunity", "attached_to_name": name}, pluck="file_url")
	for doc_type, doc_title, revision, received, attach in DOCUMENTS[title]:
		o.append("tender_documents", {"document_type": doc_type, "title": doc_title, "revision": revision, "received_on": day(received),
		                              "attachment": files[0] if attach and files else None})
	with as_user("sales"):
		o.flags.ignore_permissions = True
		o.save()
	return len(DOCUMENTS[title])


def queries(name, title):
	if frappe.db.exists("Tender Clarification", {"opportunity": name}):
		return 0
	for question, raised, answer, answered, impact in QUERIES[title]:
		with as_user("qs"):
			q = frappe.get_doc({"doctype": "Tender Clarification", "opportunity": name, "question": question, "raised_on": day(raised)})
			q.flags.ignore_permissions = True
			q.insert()
		frappe.db.set_value("Tender Clarification", q.name, {"creation": at(raised, 11)}, update_modified=False)
		if answer:
			with as_user("qs"):
				q.reload()
				q.update({"answer": answer, "answered_on": day(answered), "price_impact": 1 if impact else 0, "impact_note": impact})
				q.flags.ignore_permissions = True
				q.save()
			frappe.db.set_value("Tender Clarification", q.name, {"modified": at(answered, 15)}, update_modified=False)
	return len(QUERIES[title])
