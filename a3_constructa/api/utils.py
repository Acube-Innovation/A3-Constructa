# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""What the overview APIs share: whose company they report on.

Every overview reports on one company, the user's default, so a site holding
several companies (a demo company beside ERPNext's own sample one, say) never
adds one company's figures, or currency, to another's.
"""

import frappe


def default_company() -> str | None:
	return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)


def default_currency() -> str | None:
	company = default_company()
	if company:
		return frappe.get_cached_value("Company", company, "default_currency")
	return frappe.db.get_default("currency")


def company_projects(company: str | None) -> list[str]:
	"""The company's projects, for doctypes that carry a project but no company."""
	if not company:
		return []
	return frappe.get_all("Project", filters={"company": company}, pluck="name")


def company_filter(doctype: str, company: str | None) -> dict:
	"""{"company": ...} for a doctype that has the field; nothing for one that does not."""
	if company and frappe.get_meta(doctype).has_field("company"):
		return {"company": company}
	return {}
