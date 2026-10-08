# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Health, safety and environment on site - catalogue 6.9: toolbox talks, permits
to work and site incidents. Shared bits for the three doctypes."""

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime, today

# The standard precautions each permit type starts from (the issuer adds to them).
PRECAUTIONS = {
	"Hot work": ["Flammables cleared 10 m around the work", "Fire extinguisher at the work point", "Fire watch during and 60 minutes after",
	             "Gas cylinders upright and chained"],
	"Work at height": ["Scaffold inspected and tagged", "Harness and lanyard worn, anchored", "Edge protection or nets in place",
	                   "Area below barricaded"],
	"Excavation": ["Underground services located and marked", "Sides battered or shored beyond 1.2 m", "Edge barrier and safe access ladder",
	               "Spoil kept 1 m back from the edge"],
	"Confined space": ["Atmosphere tested (O2, LEL, H2S)", "Forced ventilation running", "Standby person and rescue plan",
	                   "Entry log kept"],
	"Electrical isolation": ["Circuit isolated and locked off", "Tested dead at the point of work", "Danger tags on the isolator",
	                         "Earthing applied where required"],
	"Lifting": ["Lift plan approved", "Crane and gear certificates in date", "Banksman appointed", "Exclusion zone set up"],
}


def default_site(doc):
	if doc.project and not doc.site:
		doc.site = frappe.db.get_value("Project", doc.project, "location")


def not_in_future(value, label):
	if value and get_datetime(value) > now_datetime():
		frappe.throw(_("{0} can't be in the future.").format(label), title=_("Date"))


def check_wbs(doc):
	if doc.get("wbs") and frappe.db.get_value("WBS", doc.wbs, "project") != doc.project:
		frappe.throw(_("WBS {0} is not part of project {1}.").format(doc.wbs, doc.project), title=_("WBS"))


def may_close_permit(doc) -> bool:
	"""The issuer signs a permit off; a project manager may stand in."""
	roles = frappe.get_roles()
	return frappe.session.user in (doc.issued_by, "Administrator") or "Constructa Project Manager" in roles or "System Manager" in roles


@frappe.whitelist()
def standard_precautions(permit_type: str) -> list[str]:
	return PRECAUTIONS.get(permit_type, [])
