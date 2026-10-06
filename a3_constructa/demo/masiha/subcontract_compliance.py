# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-09B: subcontractor back-charges and the compliance gate, on the Administrative Centre.

- Painting is subcontracted to Mbandaka Peinture et Finitions SARL: 3,200 m² at
  $2.20 (PO), 10% retention, documents all valid.
  - WC 1 (August-September, 1,400 m²): emulsion we supplied from the site store
    ($768) and cleaning paint off the window frames ($120) are deducted. Invoiced,
    the retention moved to Retention Payable, and paid.
  - WC 2 (October, 900 m²): a scaffold tower we hired for them ($150) is
    back-charged. Invoiced, not yet paid.
- The tiler's documents are on its first certificate (WC-2026-0001); its tax
  clearance ran out two days ago, so the final certificate for the last 20 m² is
  held as a draft until the renewed clearance arrives.
"""

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

from a3_constructa.demo.masiha.common import COMPANY, acc, as_user, at, comment, day, insert, log, project

PAINTER = "Mbandaka Peinture et Finitions SARL"
TILER = "Equateur Tiling Works SARL"
ITEM = "SVC-PAINT-APPL"
COST_CODE = "MSS-CC-PNT-S"
WBS = "MSS-W-PT"


def tiler_documents():
	"""What the tiler lodged with its first certificate; the tax clearance ran out two days ago."""
	return [
		{"document_type": "Insurance Certificate", "reference": "SONAS/CAR/2026/0418", "valid_until": day(200)},
		{"document_type": "Labour Compliance Certificate", "reference": "CNSS-EQ-2026-1187", "valid_until": day(60)},
		{"document_type": "Tax Clearance Certificate", "reference": "DGI/ASF/2026/3302", "valid_until": day(-2)},
	]


PAINTER_DOCUMENTS = [
	{"document_type": "Insurance Certificate", "reference": "SONAS/RC/2026/0952", "valid_until": day(150)},
	{"document_type": "Labour Compliance Certificate", "reference": "CNSS-EQ-2026-1342", "valid_until": day(45)},
	{"document_type": "Tax Clearance Certificate", "reference": "DGI/ASF/2026/3517", "valid_until": day(80)},
]


def run():
	if frappe.db.exists("Supplier", PAINTER):
		log("subcontract compliance cases already present")
		return
	tiler_wc = backfill_tiler_documents()
	po = painting_order()
	wc1, pi1 = certificate(po, "MPF-01", -50, -5, 1400, [
		("Materials supplied", "Emulsion paint issued from the site store, 12 pails", "MSS-CC-PNT-M", 768),
		("Damage", "Paint splashes cleaned off the aluminium window frames by our team", COST_CODE, 120)], certified=-3, invoiced=-2)
	pay(pi1, -1, "RWB-PAY-2026-0412")
	wc2, pi2 = certificate(po, "MPF-02", -4, 0, 900, [
		("Back-charge", "Scaffold tower hired on our account for the stair core, 1 week", COST_CODE, 150)], certified=0, invoiced=0)
	held = held_certificate()
	log(f"Painting {po}: {wc1}/{pi1} paid, {wc2}/{pi2} invoiced; tiler's documents on {tiler_wc}; {held} held: tax clearance expired")


def backfill_tiler_documents():
	"""WC-2026-0001 was certified before the compliance gate; record what the tiler lodged then."""
	wc = frappe.db.get_value("Work Certificate", {"supplier": TILER, "docstatus": 1}, "name", order_by="creation asc")
	if not wc or frappe.db.exists("Compliance Document", {"parent": wc}):
		return wc
	parent = frappe.get_doc("Work Certificate", wc)
	for i, row in enumerate(tiler_documents(), 1):
		child = frappe.get_doc({"doctype": "Compliance Document", "parent": wc, "parenttype": "Work Certificate", "parentfield": "compliance",
		                        "idx": i, "docstatus": 1, **row})
		child.db_insert()
	return parent.name


def painting_order():
	insert({"doctype": "Supplier", "supplier_name": PAINTER, "supplier_group": frappe.db.exists("Supplier Group", "Services") or "All Supplier Groups",
	        "country": "Congo, The Democratic Republic of the"})
	if not frappe.db.exists("Item", ITEM):
		insert({"doctype": "Item", "item_code": ITEM, "item_name": "Painting application, labour and tools", "item_group": "Installation",
		        "stock_uom": "Square Meter", "is_stock_item": 0, "include_item_in_manufacturing": 0, "standard_rate": 2.20,
		        "description": "Emulsion, two coats on prepared walls and ceilings: labour, tools and access up to 3 m."})
	if not frappe.db.exists("Cost Code", COST_CODE):
		insert({"doctype": "Cost Code", "cost_code": COST_CODE, "description": "Painting - application", "category": "Service",
		        "account": acc("Project Services"), "cost_center": f"Main - {frappe.get_cached_value('Company', COMPANY, 'abbr')}", "status": "Active"})
	from a3_constructa.demo.masiha.ledger import _order

	po = _order(PAINTER, ITEM, 3200, 2.20, WBS, COST_CODE, -55)
	comment("Purchase Order", po.name, "Painting subcontract: 3,200 m², 10% retention, documents to be kept current with every certificate.",
	        "pm", at(-54, 11))
	return po.name


def certificate(po, number, start, end, qty, deductions, certified, invoiced):
	with as_user("pm"):
		wc = frappe.get_doc({"doctype": "Work Certificate", "project": project(), "supplier": PAINTER, "subcontract_po": po, "wbs": WBS,
		                     "cost_head": frappe.db.get_value("WBS", WBS, "cost_head"), "certificate_no": number,
		                     "period_from": day(start), "period_to": day(end),
		                     "items": [{"item_code": ITEM, "cost_code": COST_CODE, "this_period_qty": qty, "rate": 2.20, "retention_percent": 10}],
		                     "deductions": [{"deduction_type": t, "description": d, "cost_code": c, "amount": a} for t, d, c, a in deductions]})
		if not frappe.db.exists("Work Certificate", {"supplier": PAINTER}):
			wc.compliance = []
			for row in PAINTER_DOCUMENTS:
				wc.append("compliance", row)
		wc.flags.ignore_permissions = True
		wc.flags.compliance_as_of = day(certified)
		wc.insert()
		wc.submit()
	frappe.db.set_value("Work Certificate", wc.name, {"creation": at(certified, 11), "modified": at(certified, 16)}, update_modified=False)
	with as_user("finance"):
		from a3_constructa.api.subcontract_billing import purchase_invoice_for

		pi = frappe.get_doc("Purchase Invoice", purchase_invoice_for(wc.name))
		pi.update({"set_posting_time": 1, "posting_date": day(invoiced), "bill_date": day(end), "due_date": None})
		pi.payment_schedule = []
		pi.flags.ignore_permissions = True
		pi.flags.silent_three_way = True
		pi.save()
		pi.submit()
	return wc.name, pi.name


def pay(invoice, when, reference):
	pe = get_payment_entry("Purchase Invoice", invoice, bank_account=acc("Rawbank USD"))
	pe.update({"posting_date": day(when), "reference_no": reference, "reference_date": day(when),
	           "remarks": f"Painting certificate paid, net of retention and deductions ({invoice})."})
	with as_user("finance"):
		pe.flags.ignore_permissions = True
		pe.insert()
		pe.submit()
	return pe.name


def held_certificate():
	"""The tiler's last 20 m²: its documents are copied from the first certificate, tax clearance expired."""
	po = frappe.db.get_value("Purchase Order Item", {"item_code": "SVC-TILE-INST", "docstatus": 1}, ["parent", "rate", "wbs", "cost_code"], as_dict=True)
	if not po:
		return None
	with as_user("pm"):
		wc = frappe.get_doc({"doctype": "Work Certificate", "project": project(), "supplier": TILER, "subcontract_po": po.parent, "wbs": po.wbs,
		                     "cost_head": frappe.db.get_value("WBS", po.wbs, "cost_head"), "certificate_no": "ETW-02",
		                     "period_from": day(-4), "period_to": day(0),
		                     "items": [{"item_code": "SVC-TILE-INST", "cost_code": po.cost_code, "this_period_qty": 20, "rate": po.rate,
		                                "retention_percent": 10}]})
		wc.flags.ignore_permissions = True
		wc.insert()
	comment("Work Certificate", wc.name, "Tiler's tax clearance ran out on the 4th; they say the renewal is at the DGI this week. Holding the certificate.",
	        "pm", at(0, 10))
	return wc.name
