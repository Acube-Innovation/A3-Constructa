# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Final Account - catalogue 4.7: the contract closed out, one per award.

Final contract sum:
- on a job billed by IPCs, the work as remeasured: every contract line's cumulative
  certified amount (variations are certified on the IPC lines too);
- on a job billed by milestones, the contract value plus approved variations;
- plus the agreed adjustments (claims, contra-charges, settlements). An adjustment
  not yet agreed is listed but does not count.

Settlement: what has been certified or billed for work so far, the balance the final
invoice bills, the advance still to recover, the retention held and released, and
what the client has paid. The totals rebuild whenever the account is opened. Once
the account is Agreed (submitted) its final contract sum is fixed; the settlement
figures keep following the invoices, and the account is Closed when the balance is
billed, the retention released and every invoice paid.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_constructa.a3_constructa.doctype.client_ipc.client_ipc import advance_billed
from a3_constructa.api.client_billing import retention_held

TOLERANCE = 0.005
SETTLEMENT = ("certified_to_date", "balance_due", "advance_balance", "retention_held", "retention_released", "paid_to_date",
              "outstanding_amount", "status")


class FinalAccount(Document):
	def onload(self):
		"""Totals rebuild on every refresh; a submitted account saves the settlement figures that moved."""
		if self.docstatus == 2 or not self.awarded_quotation:
			return
		before = {f: self.get(f) for f in SETTLEMENT}
		self.calculate()
		if self.docstatus == 1:
			changed = {f: self.get(f) for f in SETTLEMENT if self.get(f) != before[f]}
			if changed:
				self.db_set(changed, update_modified=False)

	def validate(self):
		award = frappe.get_doc("Awarded Quotation", self.awarded_quotation)
		if award.status == "Cancelled" or award.docstatus == 2:
			frappe.throw(_("{0} is cancelled.").format(award.name))
		other = frappe.db.get_value("Final Account", {"awarded_quotation": self.awarded_quotation, "docstatus": ["<", 2],
		                                              "name": ["!=", self.name or ""]}, "name")
		if other:
			frappe.throw(_("{0} already has final account {1}.").format(self.awarded_quotation, other), title=_("One per award"))
		self.calculate()
		if award.status != "Completed":
			frappe.msgprint(_("{0} is {1}, not yet Completed. The final account normally follows completion.").format(
				award.name, _(award.status)), title=_("Award not completed"), indicator="orange", alert=True)

	def calculate(self):
		a = frappe.get_doc("Awarded Quotation", self.awarded_quotation)
		self.customer, self.project, self.company, self.currency = a.customer, a.project, a.company, a.currency
		self.award_status = a.status
		for row in self.adjustments:
			row.currency = a.currency
		if self.docstatus == 0:
			self.contract_value = flt(a.contract_value)
			self.approved_variations = approved_variations(a.name)
			self.revised_contract_value = flt(self.contract_value + self.approved_variations, 2)
			remeasured = remeasured_value(a.name)
			by_ipc = a.get("billing_basis") == "Progress claims" and remeasured is not None
			self.remeasured_value = flt(remeasured) if by_ipc else 0
			self.measure_basis = _("Remeasured from the IPCs") if by_ipc else _("Contract plus approved variations")
			self.adjustments_total = flt(sum(flt(r.amount) for r in self.adjustments if r.agreed), 2)
			self.final_contract_sum = flt((self.remeasured_value if by_ipc else self.revised_contract_value) + self.adjustments_total, 2)
		s = settlement(a)
		self.update(s)
		self.balance_due = flt(flt(self.final_contract_sum) - s.certified_to_date, 2)
		self.status = self.status_now()

	def status_now(self):
		if self.docstatus == 0:
			return "Draft"
		settled = (abs(flt(self.balance_due)) < TOLERANCE and flt(self.retention_held) - flt(self.retention_released) < TOLERANCE
		           and flt(self.outstanding_amount) < TOLERANCE and flt(self.advance_balance) < TOLERANCE)
		return "Closed" if settled else "Agreed"

	def before_submit(self):
		open_ipcs = frappe.get_all("Client IPC", filters={"awarded_quotation": self.awarded_quotation, "docstatus": 0}, pluck="name")
		if open_ipcs:
			frappe.throw(_("Certify or delete the open certificates first: {0}.").format(", ".join(open_ipcs)), title=_("Open IPCs"))
		pending = [r.idx for r in self.adjustments if not r.agreed]
		if pending:
			frappe.msgprint(_("Adjustment rows {0} are not agreed and stay out of the final contract sum.").format(
				", ".join(str(i) for i in pending)), indicator="orange", alert=True)

	def on_submit(self):
		self.db_set("status", self.status_now())

	def on_cancel(self):
		for field in ("final_invoice", "retention_release_invoice"):
			name = self.get(field)
			if name and frappe.db.get_value("Sales Invoice", name, "docstatus") == 1:
				frappe.throw(_("Cancel invoice {0} first.").format(name))
		self.db_set("status", "Draft")


def approved_variations(award):
	return flt(frappe.db.sql("""select sum(total_amount) from `tabVariation Order`
		where awarded_quotation = %s and status = 'Approved'""", award)[0][0], 2)


def remeasured_value(award):
	"""The cumulative certified amount of every contract line, or None without certificates."""
	r = frappe.db.sql("""select count(distinct ipc.name), sum(item.this_period_amount) from `tabClient IPC Item` item
		join `tabClient IPC` ipc on ipc.name = item.parent
		where ipc.awarded_quotation = %s and ipc.docstatus = 1""", award)[0]
	return flt(r[1], 2) if r[0] else None


def award_invoices(award):
	"""The award's submitted invoices, and the earlier invoices its opening IPCs record."""
	opening = frappe.get_all("Client IPC", filters={"awarded_quotation": award, "docstatus": 1, "opening_invoice": ["is", "set"]},
	                         pluck="opening_invoice")
	fields = ["name", "net_total", "grand_total", "outstanding_amount", "is_advance_invoice", "is_retention_release", "client_ipc",
	          "final_account"]
	rows = frappe.get_all("Sales Invoice", filters={"awarded_quotation": award, "docstatus": 1}, fields=fields)
	have = {r.name for r in rows}
	extra = [n for n in opening if n not in have]
	if extra:
		rows += frappe.get_all("Sales Invoice", filters={"name": ["in", extra], "docstatus": 1}, fields=fields)
	return rows, set(opening)


def settlement(a):
	invoices, opening = award_invoices(a.name)
	ipcs = frappe.db.sql("""select sum(certified_amount), sum(advance_recovered_this_period) from `tabClient IPC`
		where awarded_quotation = %s and docstatus = 1""", a.name)[0]
	# Work billed outside the certificates: milestone invoices, the final invoice, credit notes.
	other_work = sum(flt(r.net_total) for r in invoices
	                 if not (r.is_advance_invoice or r.is_retention_release or r.client_ipc or r.name in opening))
	final_recovery = 0.0
	finals = [r.name for r in invoices if r.final_account]
	if finals:
		from a3_constructa.setup.install_defaults import CUSTOMER_ADVANCES, contract_account

		account = contract_account(a.company, CUSTOMER_ADVANCES)
		final_recovery = -flt(frappe.db.sql("""select sum(tax_amount) from `tabSales Taxes and Charges`
			where parent in %s and parenttype = 'Sales Invoice' and a3_deduction = 1 and account_head = %s""", (finals, account))[0][0])
	return frappe._dict(
		certified_to_date=flt(flt(ipcs[0]) + other_work, 2),
		advance_balance=flt(advance_billed(a.name) - flt(ipcs[1]) - final_recovery, 2),
		retention_held=flt(retention_held(a.name), 2),
		retention_released=flt(sum(flt(r.net_total) for r in invoices if r.is_retention_release), 2),
		paid_to_date=flt(sum(flt(r.grand_total) - flt(r.outstanding_amount) for r in invoices), 2),
		outstanding_amount=flt(sum(flt(r.outstanding_amount) for r in invoices), 2),
	)


@frappe.whitelist()
def make_final_invoice(final_account: str) -> str:
	from a3_constructa.api.client_billing import final_invoice

	return final_invoice(final_account)


@frappe.whitelist()
def release_remaining_retention(final_account: str) -> str:
	from a3_constructa.api.client_billing import release_remaining_retention as release

	return release(final_account)
