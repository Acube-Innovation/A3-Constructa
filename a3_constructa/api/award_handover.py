# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""From a won quotation to a running job - catalogue 3.7 (and 3.1 step 1).

1. Create Awarded Quotation on the won quotation: the award with its customer,
   value and currency, one component per cost head pointing at the tender BOQ.
2. Hand over to project on the award, in one step:
   a. the Project (created from the award, or an existing one picked);
   b. a draft Sales Order for the award, one line per component or per BOQ line;
   c. the budget BOQ, revision 0: the tender BOQ copied with stage Budget, the
      project, its quantities, and the estimate's cost rate as the budget rate,
      left in Draft for approval;
   d. the opportunity's and quotation's attachments and notes, on the project.

Every step first looks for what already exists and links it instead of making a
second one, so running the handover again only fills the gaps; get_handover_plan
says beforehand what will be created and what is already there.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from a3_constructa.a3_constructa.doctype.boq.boq import preliminaries_heads

WON_BLOCKED = ("Lost", "Cancelled", "Expired")


# ---------------------------------------------------------------- 1. the award

@frappe.whitelist()
def make_awarded_quotation(quotation: str) -> dict:
	frappe.has_permission("Awarded Quotation", "create", throw=True)
	existing = frappe.db.get_value("Awarded Quotation", {"quotation": quotation, "status": ["!=", "Cancelled"]}, "name")
	if existing:
		return {"name": existing, "existing": True}
	q = frappe.get_doc("Quotation", quotation)
	q.check_permission("read")
	if q.docstatus != 1 or q.status in WON_BLOCKED:
		frappe.throw(_("Only a submitted quotation that is still open can be awarded; {0} is {1}.").format(q.name, _(q.status)))

	customer = customer_for(q)
	title = (frappe.db.get_value("Opportunity", q.opportunity, "title") if q.opportunity else None) or q.customer_name or q.party_name
	award = frappe.new_doc("Awarded Quotation")
	award.update({
		"title": title[:140], "customer": customer, "quotation": q.name, "company": q.company, "currency": q.currency,
		"award_date": today(), "status": "Awarded",
		"scope": _("Awarded on quotation {0}, revision {1}.").format(q.name, q.get("revision_no") or 0),
	})
	for component in components_for(q):
		award.append("components", component)
	award.insert()
	if q.opportunity:
		frappe.db.set_value("Opportunity", q.opportunity, "status", "Converted")
	q.add_comment("Info", _("Awarded: {0}").format(award.name))
	return {"name": award.name, "existing": False}


def customer_for(q):
	"""The award's customer: the quotation's, or the customer made from its lead."""
	if q.quotation_to == "Customer":
		return q.party_name
	if q.quotation_to == "Lead":
		existing = frappe.db.get_value("Customer", {"lead_name": q.party_name}, "name")
		if existing:
			return existing
		from erpnext.crm.doctype.lead.lead import _make_customer

		# Winning the job turns the lead into the client: part of awarding it, so it
		# does not need the separate right to create customers.
		customer = _make_customer(q.party_name, ignore_permissions=True)
		customer.flags.ignore_permissions = True
		customer.insert()
		return customer.name
	frappe.throw(_("Make a customer for {0} first: an award needs a customer.").format(q.party_name))


def components_for(q):
	"""One component per cost head (preliminaries first, contingency last) when the
	quotation came from a BOQ; otherwise one per quotation line."""
	if not q.boq:
		return [{"component": (row.item_name or row.description or row.item_code)[:140], "description": row.description,
		         "qty": 1, "rate": flt(row.net_amount or row.amount), "uom": "Lump Sum"} for row in q.items]
	heads = OrderedDict()
	prelim = preliminaries_heads()
	ordered = sorted(q.items, key=lambda r: (2 if r.is_contingency else 0 if r.cost_head in prelim else 1, r.idx))
	for row in ordered:
		key = "__contingency" if row.is_contingency else (row.cost_head or "")
		heads.setdefault(key, 0.0)
		heads[key] += flt(row.net_amount or row.amount)
	names = dict(frappe.get_all("Cost Head", filters={"name": ["in", list(heads)]}, fields=["name", "cost_head_name"], as_list=True))
	out = []
	for key, amount in heads.items():
		label = _("Contingency") if key == "__contingency" else (names.get(key) or key or _("Other work"))
		out.append({"component": label, "cost_head": None if key == "__contingency" else key or None, "boq": q.boq,
		            "qty": 1, "rate": amount, "uom": "Lump Sum",
		            "description": _("{0} of tender BOQ {1}").format(label, q.boq)})
	return out


# ---------------------------------------------------------------- 2. the handover

@frappe.whitelist()
def get_handover_plan(award: str) -> dict:
	"""What the handover will create, and what already exists and will be linked."""
	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("read")
	tender_boqs = tender_boqs_for(a)
	sales_order = frappe.db.get_value("Sales Order", {"awarded_quotation": a.name, "docstatus": ["<", 2]}, "name")
	budget_boqs = {t: existing_budget_boq(a, t) for t in tender_boqs}
	notes = notes_to_copy(a)
	q = frappe.db.get_value("Quotation", a.quotation, ["boq"], as_dict=True) if a.quotation else None
	return {
		"award": a.name, "status": a.status, "title": a.title, "company": a.company, "customer": a.customer,
		"project": a.project,
		"project_name": a.title,
		"cost_center": frappe.get_cached_value("Company", a.company, "cost_center"),
		"start_date": a.start_date, "end_date": a.end_date,
		"sales_order": sales_order,
		"components": len(a.components),
		"boq_lines": len(frappe.get_all("Quotation Item", filters={"parent": a.quotation}, pluck="name")) if q and q.boq else 0,
		"tender_boqs": tender_boqs,
		"budget_boqs": budget_boqs,
		"attachments": len(notes["files"]),
		"notes": len(notes["comments"]) + len(notes["crm_notes"]),
	}


def tender_boqs_for(a):
	boqs = [row.boq for row in a.components if row.boq]
	return sorted({b for b in boqs if frappe.db.get_value("BOQ", b, "boq_stage") == "Tender"})


def existing_budget_boq(a, tender):
	"""The award's budget BOQ copied from `tender`, if the handover already made it."""
	for name in frappe.get_all("BOQ", filters={"awarded_quotation": a.name, "boq_stage": "Budget", "docstatus": ["<", 2]},
	                           pluck="name", order_by="creation asc"):
		if frappe.db.exists("Comment", {"reference_doctype": "BOQ", "reference_name": name, "comment_type": "Info",
		                                "content": ["like", f"%tender BOQ {tender}%"]}):
			return name
	return None


@frappe.whitelist()
def hand_over(award: str, project: str | None = None, project_name: str | None = None, cost_center: str | None = None,
              start_date: str | None = None, end_date: str | None = None, sales_order_lines: str = "Per component",
              make_sales_order: int = 1, make_budget_boq: int = 1, copy_notes: int = 1) -> dict:
	a = frappe.get_doc("Awarded Quotation", award)
	a.check_permission("write")
	if a.status not in ("Awarded", "In Progress"):
		frappe.throw(_("{0} is {1}; only an Awarded job is handed over.").format(a.name, _(a.status)))
	done = {"created": [], "linked": []}

	if start_date or end_date:
		a.update({"start_date": start_date or a.start_date, "end_date": end_date or a.end_date})
	project = ensure_project(a, project, project_name, cost_center, done)
	if a.project != project or a.has_value_changed("start_date") or a.has_value_changed("end_date"):
		a.project = project
		a.save()

	if int(make_sales_order):
		ensure_sales_order(a, sales_order_lines, done)
	if int(make_budget_boq):
		for tender in tender_boqs_for(a):
			ensure_budget_boq(a, tender, done)
	if int(copy_notes):
		copy_notes_to_project(a, done)
	a.add_comment("Info", _("Handed over to project {0}: {1}").format(
		a.project, "; ".join(done["created"] + done["linked"]) or _("nothing new")))
	return done


def ensure_project(a, project, project_name, cost_center, done):
	if a.project:
		done["linked"].append(_("project {0}").format(a.project))
		return a.project
	if project:
		frappe.has_permission("Project", "read", doc=project, throw=True)
		done["linked"].append(_("project {0}").format(project))
		return project
	frappe.has_permission("Project", "create", throw=True)
	p = frappe.new_doc("Project")
	p.update({
		"project_name": (project_name or a.title)[:140], "company": a.company, "customer": a.customer,
		"cost_center": cost_center or frappe.get_cached_value("Company", a.company, "cost_center"),
		"expected_start_date": a.start_date, "expected_end_date": a.end_date, "status": "Open",
		"notes": _("Handed over from award {0}.").format(a.name),
	})
	p.insert()
	done["created"].append(_("project {0}").format(p.name))
	return p.name


def contract_item(cost_head):
	"""The cost head's contract works item, inherited from its parents, else the default."""
	head = cost_head
	seen = set()
	while head and head not in seen:
		seen.add(head)
		item, parent = frappe.db.get_value("Cost Head", head, ["sales_item", "parent_cost_head"]) or (None, None)
		if item:
			return item
		head = parent
	item = frappe.db.get_single_value("A3 Constructa Settings", "default_contract_item")
	if not item:
		frappe.throw(_("Set a Contract Works Item on the cost head, or a Default Contract Works Item in A3 Constructa Settings."),
		             title=_("No item to bill"))
	return item


def ensure_sales_order(a, mode, done):
	existing = frappe.db.get_value("Sales Order", {"awarded_quotation": a.name, "docstatus": ["<", 2]}, "name")
	if existing:
		if not frappe.db.get_value("Sales Order", existing, "project"):
			frappe.db.set_value("Sales Order", existing, "project", a.project)
		done["linked"].append(_("sales order {0}").format(existing))
		return existing
	frappe.has_permission("Sales Order", "create", throw=True)
	delivery = a.end_date or add_days(today(), 365)
	so = frappe.new_doc("Sales Order")
	so.update({"customer": a.customer, "company": a.company, "currency": a.currency, "transaction_date": today(),
	           "delivery_date": delivery, "project": a.project, "awarded_quotation": a.name, "order_type": "Sales",
	           "po_no": a.award_reference, "po_date": a.award_date, "ignore_pricing_rule": 1})
	# Each line is 100 units, one per percent of its value, as on the project's first
	# order: a progress claim bills the percentage completed, whatever the unit measured.
	if mode == "Per BOQ line" and a.quotation and frappe.db.get_value("Quotation", a.quotation, "boq"):
		q = frappe.get_doc("Quotation", a.quotation)
		for row in q.items:
			measured = _("{0} {1} at {2}").format(frappe.format(row.qty, {"fieldtype": "Float"}), row.uom or "",
			                                     frappe.format(row.rate, {"fieldtype": "Currency", "options": "currency"}, doc=row))
			# P-04A: each line names the BOQ line it bills; the order fills in its WBS.
			so.append("items", {**line(contract_item(row.cost_head), flt(row.amount),
			                           f"{row.boq_ref or ''} {row.description or row.item_name} ({measured})".strip(), delivery),
			                    "boq": q.boq, "boq_ref": row.boq_ref, "boq_item": row.boq_item})
	else:
		for row in a.components:
			so.append("items", {**line(contract_item(row.cost_head), flt(row.amount), row.description or row.component, delivery),
			                    "boq": row.boq})
	agreed = [flt(row.rate) for row in so.items]
	so.run_method("set_missing_values")
	# The award's prices stand, whatever the selling price list says.
	for row, rate in zip(so.items, agreed):
		row.rate = row.price_list_rate = rate
		row.discount_percentage = row.discount_amount = row.margin_rate_or_amount = 0
	so.run_method("calculate_taxes_and_totals")
	so.insert()
	frappe.db.set_value("Project", a.project, "sales_order", so.name)
	done["created"].append(_("sales order {0} (draft, {1} lines)").format(so.name, len(so.items)))
	return so.name


def line(item, amount, description, delivery):
	return {"item_code": item, "qty": 100, "conversion_factor": 1, "rate": flt(amount / 100, 4), "price_list_rate": flt(amount / 100, 4),
	        "description": description, "delivery_date": delivery}


def ensure_budget_boq(a, tender, done):
	existing = existing_budget_boq(a, tender)
	if existing:
		done["linked"].append(_("budget BOQ {0}").format(existing))
		return existing
	frappe.has_permission("BOQ", "create", throw=True)
	t = frappe.get_doc("BOQ", tender)
	b = frappe.new_doc("BOQ")
	b.update({"boq_stage": "Budget", "project": a.project, "awarded_quotation": a.name, "currency": t.currency,
	          "boq_date": today(), "cost_head": t.cost_head, "opportunity": t.opportunity, "customer": a.customer,
	          "measurement_method": t.measurement_method, "revision_no": 0, "status": "Draft",
	          "contingency_amount": t.contingency_amount})
	renamed = {}
	for row in t.items:
		if row.is_contingency:
			continue  # sync_contingency rebuilds it from the header
		new_name = frappe.generate_hash(length=10)
		renamed[row.name] = new_name
		rate = flt(row.amount) if row.is_allowance else flt(row.cost_rate)
		b.append("items", {
			"name": new_name, "boq_ref": row.boq_ref, "item_code": row.item_code, "item_name": row.item_name,
			"description": row.description, "cost_head": row.cost_head, "measurement_notes": row.measurement_notes,
			"uom": row.uom, "boq_qty": row.boq_qty, "is_allowance": row.is_allowance,
			"amount": flt(row.amount) if row.is_allowance else None,
			"rate": None if row.is_allowance else rate, "cost_rate": row.cost_rate,
			"approved_qty": None if row.is_allowance else row.boq_qty, "approved_rate": None if row.is_allowance else rate,
			"draws_from_allowance": row.draws_from_allowance,
		})
	for row in b.items:
		if row.draws_from_allowance:
			row.draws_from_allowance = renamed.get(row.draws_from_allowance)
	b.insert()
	b.add_comment("Info", _("Revision 0 of the budget, copied from tender BOQ {0} at its estimated cost rates.").format(tender))
	done["created"].append(_("budget BOQ {0} (draft, {1} lines)").format(b.name, len(b.items)))
	return b.name


def notes_to_copy(a):
	sources = [("Quotation", a.quotation)] if a.quotation else []
	opp = frappe.db.get_value("Quotation", a.quotation, "opportunity") if a.quotation else None
	if opp:
		sources.append(("Opportunity", opp))
	files = frappe.get_all("File", filters={"attached_to_doctype": ["in", [s[0] for s in sources] or [""]],
	                                        "attached_to_name": ["in", [s[1] for s in sources] or [""]]},
	                       fields=["name", "file_name", "file_url", "is_private", "attached_to_doctype", "attached_to_name"])
	comments = frappe.get_all("Comment", filters={"comment_type": "Comment", "reference_doctype": ["in", [s[0] for s in sources] or [""]],
	                                              "reference_name": ["in", [s[1] for s in sources] or [""]]},
	                          fields=["content", "comment_email", "comment_by", "reference_doctype", "reference_name", "creation"],
	                          order_by="creation asc")
	crm_notes = frappe.get_all("CRM Note", filters={"parenttype": "Opportunity", "parent": opp}, fields=["note", "added_by", "added_on"],
	                           order_by="idx") if opp else []
	return {"files": files, "comments": comments, "crm_notes": crm_notes}


def copy_notes_to_project(a, done):
	notes = notes_to_copy(a)
	have_files = set(frappe.get_all("File", filters={"attached_to_doctype": "Project", "attached_to_name": a.project}, pluck="file_url"))
	have_text = set(frappe.get_all("Comment", filters={"reference_doctype": "Project", "reference_name": a.project,
	                                                   "comment_type": "Comment"}, pluck="content"))
	copied = 0
	for f in notes["files"]:
		if f.file_url in have_files:
			continue
		frappe.get_doc({"doctype": "File", "file_name": f.file_name, "file_url": f.file_url, "is_private": f.is_private,
		                "attached_to_doctype": "Project", "attached_to_name": a.project}).insert(ignore_permissions=True)
		copied += 1
	project = frappe.get_doc("Project", a.project)
	texts = [(_("From {0} {1}").format(_(c.reference_doctype), c.reference_name), c.content, c.comment_email, c.comment_by)
	         for c in notes["comments"]]
	texts += [(_("Opportunity note"), n.note, n.added_by, None) for n in notes["crm_notes"]]
	for source, content, email, by in texts:
		text = f"<p><i>{source}:</i></p>{content}"
		if text in have_text:
			continue
		project.add_comment("Comment", text, comment_email=email, comment_by=by)
		copied += 1
	if copied:
		done["created"].append(_("{0} attachments and notes copied").format(copied))
	elif notes["files"] or notes["comments"] or notes["crm_notes"]:
		done["linked"].append(_("attachments and notes already on the project"))
