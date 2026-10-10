# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Handover and the defects liability period - catalogue 6.11.

- Issue practical completion (Project): refused while any snag item on the
  project is still open or fixed-but-unverified. Sets the project's practical
  completion date and the end of its defects liability period (the award's
  defects_liability_months later), records the date on the award, and drafts the
  first half of the retention release (P-04C) for finance to submit.
- During the DLP, defects are Warranty Claims carrying the project and WBS (the
  customer comes from the project); a claim dated outside the DLP is flagged.
- End of DLP (Project): from the DLP end date, drafts the second half of the
  retention release and lists the stock still in the project's stores
  (Warehouse.project), which return_surplus turns into a draft Site Material
  Return. Defects still open are listed, not blocking.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, today

from a3_constructa.a3_constructa.doctype.snag_list.snag_list import outstanding

OPEN_CLAIMS = ("Open", "Work In Progress")
HANDOVER_ROLES = ("Constructa Project Manager", "A3 Constructa Admin", "System Manager")


def award_of(project):
	name = frappe.db.get_value("Awarded Quotation", {"project": project, "docstatus": ["<", 2]}, "name", order_by="creation desc")
	if not name:
		frappe.throw(_("{0} has no award: the defects liability period and retention come from it.").format(project), title=_("Award"))
	return frappe.get_doc("Awarded Quotation", name)


def fmt(d):
	return frappe.format(d, {"fieldtype": "Date"})


@frappe.whitelist()
def issue_practical_completion(project: str, date: str | None = None) -> dict:
	p = frappe.get_doc("Project", project)
	p.check_permission("write")
	frappe.only_for(HANDOVER_ROLES)
	if p.get("practical_completion_date"):
		frappe.throw(_("Practical completion was issued on {0}.").format(fmt(p.practical_completion_date)), title=_("Practical completion"))
	date = getdate(date or today())
	if date > getdate(today()):
		frappe.throw(_("Practical completion is issued on or after the day: {0} is in the future.").format(fmt(date)))
	snags = outstanding(project)
	if snags:
		lines = "".join(f"<li>{s.name} {frappe.utils.escape_html(s.title or '')}: {int(s.open)} open, {int(s.fixed)} fixed, not verified</li>" for s in snags)
		frappe.throw(_("Snags are still outstanding: verify them first.") + f"<ul>{lines}</ul>", title=_("Practical completion"))
	a = award_of(project)
	dlp_end = add_months(date, int(a.defects_liability_months or 0))
	p.db_set({"practical_completion_date": date, "dlp_end_date": dlp_end})
	a.db_set("practical_completion_date", date)
	release, note = None, None
	from a3_constructa.api.client_billing import draft_release, release_due, retention_held

	a.reload()
	if not flt(retention_held(a.name)):
		note = _("No retention is held, so there is nothing to release.")
	elif release_due(a, 1):
		note = release_due(a, 1)
	else:
		release = draft_release(a, 1, ignore_permissions=True)
	p.add_comment("Info", _("Practical completion issued for {0}; defects liability period to {1}.").format(fmt(date), fmt(dlp_end))
	              + (" " + _("Retention release (first half) drafted: {0}.").format(release) if release else ""))
	return {"practical_completion_date": date, "dlp_end_date": dlp_end, "retention_release": release, "note": note}


@frappe.whitelist()
def end_dlp(project: str) -> dict:
	p = frappe.get_doc("Project", project)
	p.check_permission("write")
	frappe.only_for(HANDOVER_ROLES)
	if not p.get("practical_completion_date"):
		frappe.throw(_("Issue practical completion first."), title=_("End of DLP"))
	if getdate(p.dlp_end_date) > getdate(today()):
		frappe.throw(_("The defects liability period runs to {0}.").format(fmt(p.dlp_end_date)), title=_("End of DLP"))
	a = award_of(project)
	from a3_constructa.api.client_billing import draft_release, release_due

	release, note = a.retention_release_2, None
	if not release:
		reason = release_due(a, 2)
		if reason:
			note = reason
		else:
			release = draft_release(a, 2, ignore_permissions=True)
	return {"dlp_end_date": p.dlp_end_date, "retention_release": release, "note": note, "surplus": surplus(project),
	        "open_claims": frappe.get_all("Warranty Claim", filters={"project": project, "status": ["in", OPEN_CLAIMS], "docstatus": ["<", 2]},
	                                      fields=["name", "complaint_date", "status", "wbs"], order_by="complaint_date")}


def surplus(project) -> list[dict]:
	"""Stock left in the project's stores."""
	stores = frappe.get_all("Warehouse", filters={"project": project, "is_group": 0}, pluck="name")
	if not stores:
		return []
	return frappe.db.sql("""select b.item_code, i.item_name, b.warehouse, b.actual_qty, b.stock_uom, b.stock_value
		from tabBin b join tabItem i on i.name = b.item_code
		where b.warehouse in %s and b.actual_qty > 0 order by b.stock_value desc""", [stores], as_dict=True)


@frappe.whitelist()
def return_surplus(project: str, to_warehouse: str) -> str:
	"""A draft Site Material Return of everything left in the project's stores."""
	frappe.get_doc("Project", project).check_permission("write")
	frappe.has_permission("Stock Entry", "create", throw=True)
	rows = surplus(project)
	if not rows:
		frappe.throw(_("Nothing is left in {0}'s stores.").format(project))
	if frappe.db.get_value("Warehouse", to_warehouse, "project") == project:
		frappe.throw(_("Return to a store outside the project."))
	se = frappe.get_doc({"doctype": "Stock Entry", "stock_entry_type": "Site Material Return", "purpose": "Material Transfer",
	                     "company": frappe.db.get_value("Project", project, "company"), "project": project,
	                     "remarks": _("Surplus returned at the end of the defects liability period."),
	                     "items": [{"item_code": r.item_code, "qty": r.actual_qty, "s_warehouse": r.warehouse, "t_warehouse": to_warehouse,
	                                "project": project} for r in rows]})
	se.insert()
	return se.name


# ---------------------------------------------------------------- warranty claims

def warranty_claim_defaults(doc, method=None):
	"""Before ERPNext's own validate, which wants the customer."""
	if doc.get("project"):
		customer, company = frappe.db.get_value("Project", doc.project, ["customer", "company"])
		doc.customer = doc.customer or customer
		doc.company = doc.company or company


def warranty_claim_validate(doc, method=None):
	if not doc.get("project"):
		return
	p = frappe.db.get_value("Project", doc.project, ["practical_completion_date", "dlp_end_date"], as_dict=True)
	if doc.wbs and frappe.db.get_value("WBS", doc.wbs, "project") != doc.project:
		frappe.throw(_("WBS {0} is not part of {1}.").format(doc.wbs, doc.project))
	if not p.practical_completion_date:
		frappe.msgprint(_("{0} is not yet handed over: before practical completion, defects go on a Snag List.").format(doc.project),
		                indicator="orange", alert=True)
	elif doc.complaint_date and getdate(doc.complaint_date) > getdate(p.dlp_end_date):
		frappe.msgprint(_("Reported after the defects liability period ended on {0}.").format(fmt(p.dlp_end_date)),
		                indicator="orange", alert=True)
