# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Equipment Log - catalogue 8.1 (internal rate) and 8.3: one machine's day.

Meter readings and the day's hours, split into worked, idle (on site, available,
not working) and breakdown (not available). The three never pass 24 on a day,
and the meter never runs backwards: the end reading is at least the start and at
least the last submitted log's end.

Owned plant is charged to the job at its internal hourly rate: on submit a
journal debits the cost code's account on the project, WBS and cost code, and
credits Internal Plant Recovery on the machine's cost centre; cancelling the log
cancels the journal. Hired plant logs its hours with no amount: its cost comes
through the hire order and the supplier's invoice.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_constructa.setup.install_defaults import PLANT_RECOVERY, contract_account

EQUIPMENT = "Equipment"


class EquipmentLog(Document):
	def validate(self):
		asset = frappe.db.get_value("Asset", self.asset, ["company", "project", "location", "is_hired", "internal_hourly_rate", "meter_type",
		                                                  "current_meter", "wbs", "cost_code", "docstatus", "asset_name"], as_dict=True)
		if not asset or asset.docstatus == 2:
			frappe.throw(_("Asset {0} is cancelled.").format(self.asset))
		self.set_defaults(asset)
		self.check_hours()
		self.check_meter()
		self.check_charge_to()
		self.amount = 0 if self.is_hired else flt(flt(self.worked_hours) * flt(self.internal_rate), 2)

	def set_defaults(self, asset):
		self.company = asset.company
		self.asset_name = asset.asset_name
		self.is_hired = asset.is_hired
		self.meter_type = asset.meter_type or "Hours"
		self.project = self.project or asset.project
		self.site = self.site or asset.location
		self.wbs = self.wbs or asset.wbs
		self.cost_code = self.cost_code or asset.cost_code
		if self.docstatus == 0:
			self.internal_rate = flt(asset.internal_hourly_rate)
		if not flt(self.meter_start):
			self.meter_start = last_meter(self.asset, self.log_date, self.name) or flt(asset.current_meter)

	def check_hours(self):
		hours = flt(self.worked_hours) + flt(self.idle_hours) + flt(self.breakdown_hours)
		if hours > 24:
			frappe.throw(_("Worked, idle and breakdown hours add up to {0}: a day has 24.").format(hours), title=_("Hours"))
		others = flt(frappe.db.sql("""select sum(worked_hours + idle_hours + breakdown_hours) from `tabEquipment Log`
			where asset = %s and log_date = %s and docstatus < 2 and name != %s""", (self.asset, self.log_date, self.name or ""))[0][0])
		if hours + others > 24:
			frappe.throw(_("{0} already has {1} hours logged on {2}; with this log the day would have {3}.").format(
				self.asset_name or self.asset, others, frappe.format(self.log_date, {"fieldtype": "Date"}), hours + others), title=_("Hours"))

	def check_meter(self):
		if not flt(self.meter_end):
			return  # a draft may wait for the evening reading
		if flt(self.meter_end) < flt(self.meter_start):
			frappe.throw(_("Meter end {0} is below meter start {1}.").format(flt(self.meter_end), flt(self.meter_start)), title=_("Meter"))
		last = last_meter(self.asset, self.log_date, self.name)
		if last and flt(self.meter_end) < last:
			frappe.throw(_("Meter end {0} is below the last log's reading of {1}: the meter cannot run backwards.").format(
				flt(self.meter_end), last), title=_("Meter"))

	def check_charge_to(self):
		if self.cost_code:
			category = frappe.db.get_value("Cost Code", self.cost_code, "category")
			if category != EQUIPMENT:
				frappe.throw(_("Cost code {0} is a {1} code; plant is charged to an Equipment cost code.").format(
					self.cost_code, _(category or "blank")), title=_("Cost code"))
		if self.wbs and self.project and frappe.db.get_value("WBS", self.wbs, "project") != self.project:
			frappe.throw(_("WBS {0} is not part of project {1}.").format(self.wbs, self.project))

	def before_submit(self):
		if not flt(self.meter_end):
			frappe.throw(_("Enter the meter end reading."))
		if flt(self.amount):
			missing = [_(label) for field, label in (("project", "Project"), ("cost_code", "Cost Code")) if not self.get(field)]
			if missing:
				frappe.throw(_("Owned plant is charged to the job: set {0}.").format(", ".join(missing)), title=_("Charge to the job"))
		elif not self.is_hired and flt(self.worked_hours) and not flt(self.internal_rate):
			frappe.msgprint(_("{0} has no internal hourly rate, so these hours are not charged to the job.").format(self.asset_name or self.asset),
			                indicator="orange", alert=True)

	def on_submit(self):
		if flt(self.amount):
			self.db_set("journal_entry", self.make_journal())
		update_meter(self.asset)

	def on_cancel(self):
		if self.journal_entry and frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") == 1:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			je.flags.ignore_permissions = True
			je.flags.ignore_links = True  # this log links to it
			je.cancel()
		update_meter(self.asset)

	def make_journal(self):
		recovery = contract_account(self.company, PLANT_RECOVERY)
		if not recovery:
			frappe.throw(_("Account {0} is missing for {1}. Run bench migrate to create it.").format(PLANT_RECOVERY, self.company))
		account = frappe.db.get_value("Cost Code", self.cost_code, "account")
		if not account:
			frappe.throw(_("Cost code {0} has no account.").format(self.cost_code))
		default_cc = frappe.get_cached_value("Company", self.company, "cost_center")
		job_cc = frappe.db.get_value("Project", self.project, "cost_center") or default_cc
		plant_cc = frappe.db.get_value("Asset", self.asset, "cost_center") or default_cc
		je = frappe.new_doc("Journal Entry")
		je.update({"voucher_type": "Journal Entry", "company": self.company, "posting_date": self.log_date,
		           "user_remark": _("{0}: {1} h at {2} on {3} (Equipment Log {4}).").format(
		               self.asset_name or self.asset, flt(self.worked_hours), flt(self.internal_rate), self.project, self.name)})
		je.append("accounts", {"account": account, "debit_in_account_currency": self.amount, "project": self.project, "wbs": self.wbs,
		                       "cost_code": self.cost_code, "cost_center": job_cc})
		je.append("accounts", {"account": recovery, "credit_in_account_currency": self.amount, "cost_center": plant_cc})
		je.flags.ignore_permissions = True
		je.insert()
		je.submit()
		return je.name


def last_meter(asset, on=None, exclude=None) -> float:
	"""The highest end reading on the asset's submitted logs up to `on`."""
	conditions = "asset = %(asset)s and docstatus = 1 and name != %(exclude)s"
	if on:
		conditions += " and log_date <= %(on)s"
	return flt(frappe.db.sql(f"select max(meter_end) from `tabEquipment Log` where {conditions}",
	                         {"asset": asset, "on": on, "exclude": exclude or ""})[0][0])


def update_meter(asset):
	frappe.db.set_value("Asset", asset, "current_meter", last_meter(asset), update_modified=False)


@frappe.whitelist()
def asset_defaults(asset: str) -> dict:
	"""What a new log takes from its machine. Site staff log plant without reading the
	asset register (ERPNext gives the stock roles only select on Asset), so this asks
	for Equipment Log access instead."""
	if not (frappe.has_permission("Equipment Log", "create") or frappe.has_permission("Equipment Log", "write")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	a = frappe.db.get_value("Asset", asset, ["asset_name", "company", "project", "location", "wbs", "cost_code", "is_hired",
	                                         "internal_hourly_rate", "meter_type", "current_meter"], as_dict=True)
	if not a:
		return {}
	a.meter_start = last_meter(asset) or flt(a.current_meter)
	return a
