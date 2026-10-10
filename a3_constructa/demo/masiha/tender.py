# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-02B: tender BOQs at opportunity stage, from the clients' spreadsheets.

The hospital sent its bill of quantities (NRM2) as an Excel file, the
university as a CSV. Each is attached to its opportunity, read by the same
import a user runs from "Import lines", and appended to a Tender BOQ made with
"Create > Tender BOQ". Quantities and units stay exactly as billed.
"""

import csv
import io

import frappe
from frappe.utils.xlsxutils import make_xlsx

from a3_constructa.api.boq_import import COLUMNS, make_tender_boq, read_lines
from a3_constructa.demo.masiha.common import as_user, at, comment, log

HOSPITAL = "Hospital extension: maternity and theatre block"
UNIVERSITY = "University library block"

# boq_ref, cost_head, description, uom, qty, item_code, measurement note
HOSPITAL_BILL = [
	("A/01/01", "MSS-ES", "Site clearance; strip topsoil average 150 mm and stockpile on site", "Square Meter", 2400, "", "Measured over the building footprint plus 2 m working space"),
	("A/01/02", "MSS-ES", "Excavate foundation trenches not exceeding 2 m deep; cart away surplus", "Cubic Meter", 640, "", None),
	("A/02/01", "MSS-ES", "Blinding concrete C15, 50 mm thick, under foundations", "Cubic Meter", 48, "", None),
	("A/02/03", "MSS-ES", "Reinforced concrete C30/37 in ground beams and pad foundations", "Cubic Meter", 186, "", "Net volume; no deduction for reinforcement"),
	("A/02/04", "MSS-ES", "High-yield steel reinforcement Y16, cut, bent and fixed", "Tonne", 22.5, "STL-Y16", None),
	("A/03/01", "MSS-ES", "Cement CEM II 42.5N for masonry mortar, 50 kg bags", "Bag", 1800, "CEM-425-50", None),
	("B/01/02", "MSS-AR-DW", "Aluminium windows 1200 x 1500 mm, double glazed, powder coated", "Nos", 96, "DW-ALW-1215", None),
	("B/01/05", "MSS-AR-DW", "Fire doors FD90, 900 mm single leaf, with closers", "Nos", 24, "DW-DOR-FD90", None),
	("B/03/12", "MSS-AR-FL", "Porcelain floor tiles 600 x 600 mm R10, bedded on C2TE adhesive", "Square Meter", 1850, "FIN-POR-600", "Corridors, wards and offices; theatres excluded"),
	("B/03/14", "MSS-AR-FL", "Anti-bacterial welded sheet vinyl to operating theatres, coved skirting", "Square Meter", 320, "", None),
	("B/04/02", "MSS-AR-PT", "Emulsion paint, one mist and two full coats, internal walls", "Square Meter", 5400, "", "Measured both sides of internal walls"),
	("C/01/04", "MSS-MEP", "Single-core 4 mm² cable drawn into conduit", "Meter", 7200, "ELE-CBL-4", None),
	("C/02/01", "MSS-MEP", "Medical gas outlets, oxygen and vacuum, wall mounted", "Nos", 64, "", None),
	("C/03/01", "MSS-MEP", "Standby diesel generator 250 kVA, installed and commissioned", "Lump Sum", 1, "", None),
]

UNIVERSITY_BILL = [
	("1.1", "MSS-ES", "Reinforced concrete C30/37 to slabs and beams", "Cubic Meter", 410, ""),
	("1.2", "MSS-ES", "Blockwork 200 mm hollow concrete blocks", "Square Meter", 1650, ""),
	("2.1", "MSS-AR-FL", "Porcelain floor tiles 600 x 600 mm R10 to reading rooms", "Square Meter", 980, "FIN-POR-600"),
	("2.2", "MSS-AR-PT", "Emulsion paint, two coats, to walls and ceilings", "Square Meter", 3900, ""),
	("3.1", "MSS-AR-DW", "Aluminium windows 1200 x 1500 mm, double glazed", "Nos", 58, "DW-ALW-1215"),
	("4.1", "MSS-MEP", "Single-core 4 mm² cable drawn into conduit", "Meter", 2600, "ELE-CBL-4"),
]


def run():
	from a3_constructa.demo.masiha.setup import create_users

	create_users()  # gives the QS her Sales User role on a site built before P-02B
	made = []
	for title, filename, content, notes in (
		(HOSPITAL, "hospital-bill-of-quantities.xlsx", _xlsx(HOSPITAL_BILL), {r[0]: r[6] for r in HOSPITAL_BILL if r[6]}),
		(UNIVERSITY, "university-library-boq.csv", _csv(UNIVERSITY_BILL), {}),
	):
		opp = frappe.db.get_value("Opportunity", {"title": title}, "name")
		if not opp or frappe.db.exists("BOQ", {"opportunity": opp, "boq_stage": "Tender"}):
			continue
		made.append(_tender(opp, filename, content, notes))
	log("tender BOQs: " + (", ".join(made) or "already present"))


def _xlsx(bill):
	return make_xlsx([list(COLUMNS)] + [list(r[:6]) for r in bill], "Bill").getvalue()


def _csv(bill):
	out = io.StringIO()
	writer = csv.writer(out)
	writer.writerow(COLUMNS)
	writer.writerows(bill)
	return out.getvalue().encode("utf-8")


def _tender(opp, filename, content, notes):
	with as_user("sales"):
		file = frappe.get_doc({"doctype": "File", "file_name": filename, "attached_to_doctype": "Opportunity",
		                      "attached_to_name": opp, "content": content, "is_private": 1})
		file.insert(ignore_permissions=True)
	with as_user("qs"):
		result = read_lines(file.file_url)
		if result["errors"]:
			frappe.throw("; ".join(result["errors"]))
		boq = frappe.get_doc(make_tender_boq(opp))
		boq.boq_date = frappe.utils.add_days(frappe.utils.today(), -3)
		for row in result["rows"]:
			boq.append("items", {k: row[k] for k in ("boq_ref", "cost_head", "description", "uom", "boq_qty", "item_code")}
			           | {"measurement_notes": notes.get(row["boq_ref"])})
		boq.flags.ignore_permissions = True
		boq.insert()
	comment("BOQ", boq.name, f"Imported {len(result['rows'])} lines from the client's {filename}. Rates to follow from the estimate.", "qs", at(-3, 15))
	return f"{boq.name} ({len(result['rows'])} lines from {filename})"
