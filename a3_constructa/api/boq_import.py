# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 2.4: a tender BOQ at opportunity stage, and BOQ lines from a spreadsheet.

The client's bill usually arrives as a spreadsheet. "Import lines" on a BOQ
reads an .xlsx or .csv with the columns boq_ref, cost_head, description, uom,
qty and (optionally) item_code, checks every row, and hands back the lines to
preview and append. Nothing is appended when any row fails: the errors name
each row by its number in the sheet, so the file can be fixed and loaded
again. Quantities and units are kept exactly as the bill states them.
"""

import frappe
from frappe import _
from frappe.utils import cstr
from frappe.utils.csvutils import read_csv_content
from frappe.utils.xlsxutils import make_xlsx, read_xlsx_file_from_attached_file

COLUMNS = ("boq_ref", "cost_head", "description", "uom", "qty", "item_code")
REQUIRED = ("cost_head", "description", "uom", "qty")
TEMPLATE_ROWS = [
	("A/01/01", "MSS-ES", "Excavate to reduce levels, average 0.5 m deep, cart away", "Cubic Meter", 420, ""),
	("A/02/03", "MSS-ES", "Reinforced concrete C30/37 in ground beams", "Cubic Meter", 86.5, ""),
	("B/03/12", "MSS-AR-FL", "Porcelain floor tiles 600 x 600 mm R10, bedded on adhesive", "Square Meter", 1250, "FIN-POR-600"),
	("C/01/04", "MSS-MEP", "Supply and install 4 mm² cable in conduit", "Meter", 3600, ""),
]


@frappe.whitelist()
def make_tender_boq(opportunity: str):
	"""A new, unsaved Tender BOQ for the opportunity: its client and currency set,
	ready for the client's bill to be imported."""
	frappe.has_permission("Opportunity", "read", opportunity, throw=True)
	frappe.has_permission("BOQ", "create", throw=True)
	opp = frappe.get_doc("Opportunity", opportunity)
	boq = frappe.new_doc("BOQ")
	boq.update({
		"boq_stage": "Tender",
		"opportunity": opp.name,
		"client_name": opp.customer_name,
		"customer": opp.party_name if opp.opportunity_from == "Customer" else None,
		"currency": opp.currency or frappe.get_cached_value("Company", opp.company, "default_currency"),
		"measurement_method": "NRM2",
	})
	return boq.as_dict()


@frappe.whitelist()
def read_lines(file_url: str) -> dict:
	"""Read and check a bill. Returns {"rows": [...], "errors": [...]}; rows are only
	returned when there are no errors, so a bad sheet appends nothing."""
	frappe.has_permission("BOQ", "write", throw=True)
	table = _read_table(file_url)
	if not table:
		return {"rows": [], "errors": [_("The file is empty.")]}

	header = [cstr(h).strip().lower().replace(" ", "_") for h in table[0]]
	missing = [c for c in REQUIRED if c not in header]
	if missing:
		return {"rows": [], "errors": [_("Row 1 (headings): missing column(s) {0}. Expected: {1}.").format(
			", ".join(missing), ", ".join(COLUMNS))]}
	col = {name: header.index(name) for name in COLUMNS if name in header}

	uoms = {u.lower(): u for u in frappe.get_all("UOM", pluck="name")}
	heads = set(frappe.get_all("Cost Head", pluck="name"))
	rows, errors = [], []
	for number, values in enumerate(table[1:], start=2):
		get = lambda name: cstr(values[col[name]]).strip() if name in col and col[name] < len(values) and values[col[name]] is not None else ""
		if not any(get(name) for name in col):
			continue  # blank line between sections of the bill
		problems = []
		uom = uoms.get(get("uom").lower())
		if not uom:
			problems.append(_("unknown UOM '{0}'").format(get("uom")) if get("uom") else _("no UOM"))
		head = get("cost_head")
		if head not in heads:
			problems.append(_("unknown cost head '{0}'").format(head) if head else _("no cost head"))
		if not get("description"):
			problems.append(_("no description"))
		try:
			qty = float(get("qty").replace(",", ""))
			if qty <= 0:
				problems.append(_("quantity must be more than zero"))
		except ValueError:
			problems.append(_("quantity '{0}' is not a number").format(get("qty")))
			qty = 0
		item = get("item_code")
		if item and not frappe.db.exists("Item", item):
			problems.append(_("unknown item '{0}'").format(item))
		if problems:
			errors.append(_("Row {0}: {1}.").format(number, "; ".join(problems)))
			continue
		rows.append({"boq_ref": get("boq_ref") or None, "cost_head": head, "description": get("description"),
		             "uom": uom, "boq_qty": qty, "item_code": item or None, "sheet_row": number})
	if errors:
		return {"rows": [], "errors": errors}
	if not rows:
		return {"rows": [], "errors": [_("No lines found under the headings.")]}
	return {"rows": rows, "errors": []}


def _read_table(file_url):
	name = file_url.lower()
	if name.endswith(".xlsx"):
		return read_xlsx_file_from_attached_file(file_url=file_url)
	if name.endswith(".csv"):
		file = frappe.get_doc("File", {"file_url": file_url})
		return read_csv_content(file.get_content())
	frappe.throw(_("Upload the bill as an .xlsx or .csv file."))


@frappe.whitelist()
def download_template():
	"""An .xlsx with the expected headings and four example lines."""
	frappe.has_permission("BOQ", "read", throw=True)
	data = [list(COLUMNS)] + [list(r) for r in TEMPLATE_ROWS]
	xlsx = make_xlsx(data, "BOQ lines", column_widths=[12, 14, 60, 14, 10, 16])
	frappe.response["filename"] = "boq_import_template.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
