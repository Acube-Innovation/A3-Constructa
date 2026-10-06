"""P-02E: selling rates are now rounded to the cent, as quoted; recompute the
pricing of every draft BOQ so its selling total matches its quotation."""

import frappe

from a3_constructa.a3_constructa.doctype.boq.boq import refresh_pricing


def execute():
	if not frappe.db.has_column("BOQ", "selling_total"):
		return
	for name in frappe.get_all("BOQ", filters={"docstatus": 0}, pluck="name"):
		refresh_pricing(name)
