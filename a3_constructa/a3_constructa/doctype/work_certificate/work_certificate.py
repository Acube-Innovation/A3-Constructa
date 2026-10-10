# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Work Certificate - the subcontractor's interim certificate (catalogue 9.6).

Each line certifies this period's quantity of a subcontract PO line; previous and
this period together may not pass the contracted quantity. From the certified
amount come retention (released at the end of the defects liability period) and
the deductions: back-charges, damage, materials we supplied, penalties, each on
the WBS and cost code it recovers. Net payable now = amount - retention -
deductions.

A blocking Mandatory Document Rule for Work Certificate lists the documents the
subcontractor must hold (insurance, labour compliance, tax clearance); the
certificate cannot be submitted while one is missing or expired.

"Create Purchase Invoice" turns a submitted certificate into the supplier's
invoice (see api/subcontract_billing.py).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate, today


class WorkCertificate(Document):
	def onload(self):
		if self.docstatus == 0:
			self.set_onload("compliance_issues", self.compliance_issues())

	def before_insert(self):
		self.copy_compliance()

	def validate(self):
		self.set_from_po()
		self.calculate_amounts()
		self.validate_quantities()

	def before_submit(self):
		issues = self.compliance_issues()
		if issues:
			frappe.throw(_("{0} cannot be certified until its compliance documents are in order:<br>{1}").format(
				self.supplier, "<br>".join(issues)), title=_("Compliance documents"))

	def on_cancel(self):
		if self.purchase_invoice and frappe.db.get_value("Purchase Invoice", self.purchase_invoice, "docstatus") == 1:
			frappe.throw(_("Cancel purchase invoice {0} first.").format(self.purchase_invoice))

	def set_from_po(self):
		"""On a subcontract PO, the contracted quantity is the PO's and the previous
		quantity what earlier certificates on that PO certified."""
		if not self.subcontract_po:
			return
		for row in self.items:
			ordered = frappe.db.get_value("Purchase Order Item", {"parent": self.subcontract_po, "item_code": row.item_code}, "sum(qty)")
			if ordered and not flt(row.contracted_qty):
				row.contracted_qty = flt(ordered)
			if self.docstatus == 0:
				row.previous_qty = flt(frappe.db.sql("""select sum(item.this_period_qty) from `tabWork Certificate Item` item
					join `tabWork Certificate` wc on wc.name = item.parent
					where wc.subcontract_po = %s and wc.docstatus = 1 and wc.name != %s and item.item_code = %s""",
					(self.subcontract_po, self.name or "", row.item_code))[0][0])

	def calculate_amounts(self):
		"""Certify this period's work, then take off retention and the deductions."""
		total = retention = 0.0
		for row in self.items:
			row.amount = flt(row.this_period_qty) * flt(row.rate)
			row.retention_amount = flt(row.amount) * flt(row.retention_percent) / 100.0
			row.net_payable = flt(row.amount) - flt(row.retention_amount)
			total += flt(row.amount)
			retention += flt(row.retention_amount)
		for row in self.deductions:
			row.wbs = row.wbs or self.wbs
		deductions = sum(flt(r.amount) for r in self.deductions)
		self.total_amount = flt(total, 2)
		self.total_retention = flt(retention, 2)
		self.total_deductions = flt(deductions, 2)
		self.total_net_payable = flt(total - retention - deductions, 2)
		if self.total_net_payable < 0:
			frappe.throw(_("The deductions ({0}) are more than the certified amount less retention ({1}).").format(
				frappe.format(deductions, {"fieldtype": "Currency"}), frappe.format(total - retention, {"fieldtype": "Currency"})),
				title=_("Deductions"))

	def validate_quantities(self):
		"""Certifying more than was contracted is the error worth catching here."""
		for row in self.items:
			if not flt(row.contracted_qty):
				continue
			certified = flt(row.previous_qty) + flt(row.this_period_qty)
			if certified > flt(row.contracted_qty) + 1e-9:
				frappe.throw(
					_("Row {0}: certified quantity {1} exceeds the contracted quantity {2} for {3}.").format(
						row.idx, certified, flt(row.contracted_qty), row.item_code
					)
				)

	# ------------------------------------------------------------ compliance

	def copy_compliance(self):
		"""A new certificate starts with the documents on the subcontractor's last one."""
		if self.compliance or not self.supplier:
			return
		last = frappe.db.get_value("Work Certificate", {"supplier": self.supplier, "docstatus": ["<", 2]}, "name", order_by="creation desc")
		if not last:
			return
		for row in frappe.get_all("Compliance Document", filters={"parent": last, "parenttype": "Work Certificate"},
		                          fields=["document_type", "reference", "valid_until", "attachment"], order_by="idx"):
			self.append("compliance", row)

	def compliance_issues(self) -> list[str]:
		"""Each required document that is missing or expired, by name. Expiry is judged
		on the day of submission; code that records a certificate after the fact (the
		demo's story) may set flags.compliance_as_of to the day it was certified."""
		as_of = getdate(self.flags.compliance_as_of or today())
		required = required_documents(self.project)
		if not required:
			return []
		on_file = {}
		for row in self.compliance:
			if row.document_type:
				best = on_file.get(row.document_type)
				# A document without an expiry beats any dated one; otherwise the latest date counts.
				if best is None or (best.valid_until and (not row.valid_until or getdate(row.valid_until) > getdate(best.valid_until))):
					on_file[row.document_type] = row
		issues = []
		for doc_type in required:
			row = on_file.get(doc_type)
			if not row:
				issues.append(_("{0}: missing").format(frappe.bold(doc_type)))
			elif row.valid_until and getdate(row.valid_until) < as_of:
				issues.append(_("{0}: expired on {1}").format(frappe.bold(doc_type), formatdate(row.valid_until)))
		return issues


def required_documents(project=None) -> list[str]:
	"""The document types blocking Mandatory Document Rules require on a Work Certificate."""
	out = []
	for rule in frappe.get_all("Mandatory Document Rule", filters={"reference_doctype": "Work Certificate", "is_blocking": 1},
	                           fields=["name", "applicable_project"]):
		if rule.applicable_project and rule.applicable_project != project:
			continue
		for t in frappe.get_all("Mandatory Document Rule Item", filters={"parent": rule.name, "parenttype": "Mandatory Document Rule"},
		                        pluck="document_type", order_by="idx"):
			if t not in out:
				out.append(t)
	return out


@frappe.whitelist()
def make_purchase_invoice(work_certificate: str) -> str:
	from a3_constructa.api.subcontract_billing import purchase_invoice_for

	return purchase_invoice_for(work_certificate)
