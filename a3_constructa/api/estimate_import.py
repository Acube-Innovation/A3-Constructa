# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 2.5: estimate sheets for a BOQ's lines, and their resources from a spreadsheet.

An Estimate Sheet prices one BOQ line. Besides opening it from the line itself:

- "Estimate sheets for every line" on a BOQ (or the sheet list) creates the
  missing sheets in one go;
- a new sheet started from the list asks which line it prices;
- "Import estimates" on a BOQ reads one .xlsx/.csv for all its lines (a
  boq_ref column says which line each resource belongs to), and "Import
  resources" on a sheet reads the rows for that sheet's line.

Columns: boq_ref, line (the line's description, for reading only), resource_type,
item_code, description, uom, qty_per_unit, wastage_percent, output_per_day, rate.
A row with no resource is skipped, so the template can list every line before
it is filled. A blank rate on an item is fetched as "Fetch prices" would. As
with BOQ lines, nothing is imported when any row fails.
"""

import frappe
from frappe import _
from frappe.utils import cstr, flt

from a3_constructa.api.boq_import import _read_table
from a3_constructa.a3_constructa.doctype.estimate_sheet.estimate_sheet import open_for_line

COLUMNS = ("boq_ref", "line", "resource_type", "item_code", "description", "uom", "qty_per_unit", "wastage_percent", "output_per_day", "rate")
TYPES = ("Material", "Labour", "Equipment", "Subcontract", "Other")
PER_DAY = ("Labour", "Equipment")
EXAMPLE = [
	("B/03/12", "Porcelain floor tiles 600 x 600 mm", "Material", "FIN-POR-600", "", "Square Meter", 1, 5, "", ""),
	("B/03/12", "", "Material", "FIN-ADH-C2", "", "Bag", 0.2, 5, "", ""),
	("B/03/12", "", "Labour", "", "Tiler and helper, day rate", "Day", "", "", 18, 45),
	("B/03/12", "", "Equipment", "", "Tile cutter and mixer, day rate", "Day", "", "", 18, 12),
]


def lines_of(boq):
	"""The BOQ's saved lines that can be priced (not allowances)."""
	return frappe.get_all("BOQ Item", filters={"parent": boq, "parenttype": "BOQ", "is_allowance": 0},
	                      fields=["name", "idx", "boq_ref", "description", "item_name", "uom", "boq_qty", "estimate_sheet"], order_by="idx")


@frappe.whitelist()
def boq_lines(boq: str) -> list[dict]:
	"""For the line picker on a new sheet."""
	frappe.has_permission("BOQ", "read", boq, throw=True)
	return lines_of(boq)


@frappe.whitelist()
def make_sheets(boq: str) -> dict:
	"""An Estimate Sheet for every priceable line of the BOQ that has none."""
	frappe.has_permission("BOQ", "read", boq, throw=True)
	if frappe.db.get_value("BOQ", boq, "docstatus") != 0:
		frappe.throw(_("{0} is approved; its estimates are closed.").format(boq))
	made = [open_for_line(boq, line.name) for line in lines_of(boq) if not line.estimate_sheet]
	return {"made": made, "lines": len(lines_of(boq))}


@frappe.whitelist()
def read_resources(file_url: str, boq: str, boq_item: str | None = None) -> dict:
	"""Check a resources sheet. With boq_item (a sheet's own import), every row is for
	that line unless its boq_ref names another, which is left out.
	Returns {"lines": {boq_item: [rows]}, "refs": {boq_item: label}, "errors": [...], "skipped": n}."""
	frappe.has_permission("Estimate Sheet", "write", throw=True)
	table = _read_table(file_url)
	if not table:
		return {"lines": {}, "errors": [_("The file is empty.")], "skipped": 0}
	header = [cstr(h).strip().lower().replace(" ", "_") for h in table[0]]
	need = ["resource_type"] + ([] if boq_item else ["boq_ref"])
	missing = [c for c in need if c not in header]
	if missing:
		return {"lines": {}, "errors": [_("Row 1 (headings): missing column(s) {0}. Expected: {1}.").format(
			", ".join(missing), ", ".join(COLUMNS))], "skipped": 0}
	col = {name: header.index(name) for name in COLUMNS if name in header}

	all_lines = lines_of(boq)
	refs = {cstr(l.boq_ref).strip(): l for l in all_lines if l.boq_ref}
	own = next((l for l in all_lines if l.name == boq_item), None) if boq_item else None
	if boq_item and not own:
		return {"lines": {}, "errors": [_("That line is not a priceable line of {0}.").format(boq)], "skipped": 0}
	uoms = {u.lower(): u for u in frappe.get_all("UOM", pluck="name")}
	types = {t.lower(): t for t in TYPES}
	lines, errors, skipped = {}, [], 0
	for number, values in enumerate(table[1:], start=2):
		get = lambda name: cstr(values[col[name]]).strip() if name in col and col[name] < len(values) and values[col[name]] is not None else ""
		if not any(get(n) for n in ("resource_type", "item_code", "description", "qty_per_unit", "output_per_day", "rate")):
			continue  # a line listed but not yet priced, or a blank row
		ref = get("boq_ref")
		if own and ref and ref != cstr(own.boq_ref).strip():
			skipped += 1
			continue
		line = own or refs.get(ref)
		problems = []
		if not line:
			problems.append(_("no line '{0}' in {1}").format(ref, boq) if ref else _("no boq_ref"))
		kind = types.get(get("resource_type").lower())
		if not kind:
			problems.append(_("resource_type must be one of {0}").format(", ".join(TYPES)))
		item = get("item_code")
		if item and not frappe.db.exists("Item", item):
			problems.append(_("unknown item '{0}'").format(item))
		uom = uoms.get(get("uom").lower()) if get("uom") else None
		if get("uom") and not uom:
			problems.append(_("unknown UOM '{0}'").format(get("uom")))
		if not item and not get("description"):
			problems.append(_("an item or a description is needed"))
		numbers = {}
		for name in ("qty_per_unit", "wastage_percent", "output_per_day", "rate"):
			try:
				numbers[name] = float(get(name).replace(",", "")) if get(name) else 0  # flt() would read "x" as 0
				if numbers[name] < 0:
					problems.append(_("{0} cannot be negative").format(name))
			except ValueError:
				problems.append(_("{0} '{1}' is not a number").format(name, get(name)))
				numbers[name] = 0
		if kind in PER_DAY and not numbers.get("output_per_day"):
			problems.append(_("{0} needs output_per_day (BOQ units a day)").format(kind))
		if kind and kind not in PER_DAY and not numbers.get("qty_per_unit"):
			problems.append(_("{0} needs qty_per_unit").format(kind))
		if not item and not numbers.get("rate"):
			problems.append(_("a rate is needed when there is no item to price"))
		if problems:
			errors.append(_("Row {0}: {1}.").format(number, "; ".join(problems)))
			continue
		lines.setdefault(line.name, []).append({
			"resource_type": kind, "item_code": item or None,
			"description": get("description") or (frappe.get_cached_value("Item", item, "item_name") if item else ""),
			"uom": uom, "qty_per_unit": numbers["qty_per_unit"],
			"wastage_percent": numbers["wastage_percent"] if kind == "Material" else 0,
			"output_per_day": numbers["output_per_day"], "rate": numbers["rate"],
			"rate_source": "Manual" if numbers["rate"] else "Price List", "sheet_row": number,
		})
	if errors:
		return {"lines": {}, "errors": errors, "skipped": skipped}
	if not lines:
		return {"lines": {}, "errors": [_("No resources found under the headings.")], "skipped": skipped}
	by_name = {l.name: l for l in all_lines}
	return {"lines": lines, "errors": [], "skipped": skipped,
	        "refs": {n: by_name[n].boq_ref or _("Line {0}").format(by_name[n].idx) for n in lines},
	        "replaces": [n for n in lines if by_name[n].estimate_sheet]}


@frappe.whitelist()
def import_estimates(boq: str, file_url: str) -> dict:
	"""Write the checked resources to each line's sheet (created if missing),
	replacing what the sheet had; prices are fetched for items with no rate."""
	frappe.has_permission("Estimate Sheet", "create", throw=True)
	if frappe.db.get_value("BOQ", boq, "docstatus") != 0:
		frappe.throw(_("{0} is approved; its estimates are closed.").format(boq))
	checked = read_resources(file_url, boq)
	if checked["errors"]:
		frappe.throw("<br>".join(checked["errors"]), title=_("Nothing imported"))
	done = []
	for line, rows in checked["lines"].items():
		sheet = frappe.get_doc("Estimate Sheet", open_for_line(boq, line))
		fill(sheet, rows)
		sheet.save()
		done.append({"sheet": sheet.name, "boq_ref": checked["refs"][line], "resources": len(rows), "unit_cost": sheet.unit_cost})
	return {"sheets": done}


def fill(sheet, rows):
	sheet.set("resources", [])
	for row in rows:
		sheet.append("resources", {k: v for k, v in row.items() if k != "sheet_row"})
	sheet.fetch_prices()


@frappe.whitelist()
def download_template(boq: str | None = None):
	"""The headings with every line of the BOQ listed (or example rows), ready to fill."""
	from frappe.utils.xlsxutils import make_xlsx

	data = [list(COLUMNS)]
	if boq and frappe.db.exists("BOQ", boq):
		frappe.has_permission("BOQ", "read", boq, throw=True)
		for line in lines_of(boq):
			data.append([line.boq_ref, (line.description or line.item_name or "")[:120]] + [""] * (len(COLUMNS) - 2))
	else:
		data += [list(r) for r in EXAMPLE]
	xlsx = make_xlsx(data, "Resources", column_widths=[10, 40, 14, 16, 34, 14, 12, 14, 14, 10])
	frappe.response["filename"] = f"estimate_resources_{boq or 'template'}.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
