# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 9.3 and 14.2: approval levels and the budget check on requests and orders.

The Approval Matrix says, per document type, project, item group and value
band, which level of approval a document needs and who gives each level. A
Material Request or Purchase Order:

- on save, works out the level it needs: the highest level whose row matches;
- is approved level by level, each level by its matrix user or role, through
  the Approve / Reject buttons; every action is kept in its Approval Log;
- can be submitted only when every level up to the one it needs has approved;
- on submit, is checked against the budget of each WBS and cost code it
  charges, as A3 Constructa Settings say (warn, stop, or off).

A site workflow (such as Masiha's PR and PO approval) keeps working: its
submitting step is refused until the levels are done, and when the last level
is approved by someone who may also take that step, it is taken for them.
"""

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow_name
from frappe.utils import cint, flt, fmt_money, now_datetime

from a3_constructa.api.budget_allocation import wbs_budget, wbs_committed_and_actual

DOCTYPES = ("Material Request", "Purchase Order")


# ---------------------------------------------------------------- matrix
def document_value(doc):
	"""Value the matrix bands are read against: the order total, or for a request
	its lines at their rate (valuation or last purchase rate where none is set)."""
	if doc.doctype == "Purchase Order":
		return flt(doc.base_grand_total or doc.grand_total)
	total = 0
	for row in doc.items:
		rate = flt(row.rate) or flt(
			frappe.get_cached_value("Item", row.item_code, "valuation_rate")
			or frappe.get_cached_value("Item", row.item_code, "last_purchase_rate")
		)
		total += flt(row.stock_qty or row.qty) * rate
	return total


def matrix_rows(doc):
	"""Active matrix rows for this doctype that fit the document's projects and item groups."""
	projects = {doc.get("project")} | {row.get("project") for row in doc.items}
	projects.discard(None)
	groups = {row.item_group or frappe.get_cached_value("Item", row.item_code, "item_group") for row in doc.items if row.item_code}
	rows = frappe.get_all(
		"Approval Matrix",
		filters={"reference_doctype": doc.doctype, "is_active": 1},
		fields=["name", "project", "category", "amount_from", "amount_to", "approval_level", "approver_role", "approver_user"],
		order_by="approval_level",
	)
	return [r for r in rows if (not r.project or r.project in projects) and (not r.category or in_category(groups, r.category))]


def in_category(groups, category):
	bounds = frappe.get_cached_value("Item Group", category, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return category in groups
	for group in groups:
		g = frappe.get_cached_value("Item Group", group, ["lft", "rgt"], as_dict=True)
		if g and bounds.lft <= g.lft and g.rgt <= bounds.rgt:
			return True
	return False


def required_level(doc, rows=None):
	rows = matrix_rows(doc) if rows is None else rows
	value = document_value(doc)
	matching = [
		r.approval_level for r in rows
		if flt(r.amount_from) <= value and (not flt(r.amount_to) or value < flt(r.amount_to))
	]
	return max(matching or [0])


def levels_up_to(rows, required):
	"""The levels to pass, in order, and who gives each."""
	out = {}
	for r in rows:
		if 0 < r.approval_level <= required:
			out.setdefault(r.approval_level, []).append(r)
	return dict(sorted(out.items()))


def next_level(doc, rows=None):
	rows = matrix_rows(doc) if rows is None else rows
	for level, approvers in levels_up_to(rows, cint(doc.approval_level_required)).items():
		if level > cint(doc.approval_level_reached):
			return level, approvers
	return None, []


def describe(approvers):
	names = []
	for a in approvers:
		names.append(frappe.utils.get_fullname(a.approver_user) if a.approver_user else a.approver_role)
	return " / ".join(dict.fromkeys(n for n in names if n)) or _("nobody set in the Approval Matrix")


def can_approve(approvers, user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	return any((a.approver_user and a.approver_user == user) or (not a.approver_user and a.approver_role in roles) for a in approvers)


# ---------------------------------------------------------------- hooks
def set_required_level(doc, method=None):
	"""validate: the level this document needs. If its value or the level it needs
	changes after someone approved it, the approvals no longer cover it."""
	if doc.docstatus != 0:
		return
	if doc.is_new():
		# A copy or an amendment starts unapproved, whatever it was copied from.
		doc.approval_level_reached = 0
		doc.set("approvals", [])
	required = required_level(doc)
	before = doc.get_doc_before_save() if not doc.is_new() else None
	changed = before and (
		abs(document_value(before) - document_value(doc)) > 0.005 or cint(before.approval_level_required) != required
	)
	doc.approval_level_required = required
	if changed and cint(doc.approval_level_reached):
		doc.approval_level_reached = 0
		frappe.msgprint(_("The value changed after it was approved, so it needs approving again."), alert=True, indicator="orange")


def check_levels_before_submit(doc, method=None):
	"""before_submit: every level up to the one needed must have approved."""
	required = required_level(doc)
	doc.approval_level_required = required
	if cint(doc.approval_level_reached) >= required:
		return
	rows = matrix_rows(doc)
	missing = [
		_("level {0}: {1}").format(level, describe(approvers))
		for level, approvers in levels_up_to(rows, required).items()
		if level > cint(doc.approval_level_reached)
	]
	frappe.throw(
		_("{0} needs approval before it can be submitted. Still to approve: {1}.").format(doc.name, "; ".join(missing)),
		title=_("Approval needed"),
	)


def check_budget(doc, method=None):
	"""before_submit: this document plus open orders plus actual cost, against the
	budget of each WBS and cost code it charges."""
	settings = frappe.get_cached_doc("A3 Constructa Settings")
	action = settings.budget_check_action or "Warn"
	if action == "Off":
		return
	if doc.doctype == "Material Request" and doc.material_request_type != "Purchase":
		return
	tolerance = flt(settings.budget_tolerance_percent)

	asking = {}
	for row in doc.items:
		if not row.get("wbs"):
			continue
		key = (row.wbs, row.get("cost_code") or None)
		if doc.doctype == "Purchase Order":
			amount = flt(row.base_net_amount or row.base_amount)
		else:
			rate = flt(row.rate) or flt(frappe.get_cached_value("Item", row.item_code, "valuation_rate") or frappe.get_cached_value("Item", row.item_code, "last_purchase_rate"))
			amount = flt(row.stock_qty or row.qty) * rate
		asking[key] = asking.get(key, 0) + amount

	currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	money = lambda v: fmt_money(v, currency=currency)
	over = []
	for (wbs, cost_code), amount in asking.items():
		project = frappe.db.get_value("WBS", wbs, "project")
		if not project:
			continue
		budget = wbs_budget(project, wbs, cost_code)
		committed, actual = wbs_committed_and_actual(project, wbs, cost_code)
		if committed + actual + amount > budget * (1 + tolerance / 100) + 0.005:
			where = frappe.bold(wbs) + (f" / {cost_code}" if cost_code else "")
			over.append(
				_("{0}: budget {1}, already committed {2}, spent {3}, this {4} brings it to {5}, {6} over.").format(
					where, money(budget), money(committed), money(actual), money(amount),
					money(committed + actual + amount), frappe.bold(money(committed + actual + amount - budget)),
				)
			)
	if not over:
		return
	message = "<br>".join(over)
	if tolerance:
		message += "<br>" + _("Tolerance allowed: {0}%.").format(tolerance)
	if action == "Stop":
		frappe.throw(message + "<br>" + _("Move budget with a Budget Transfer, or reduce this document."), title=_("Over budget"))
	frappe.msgprint(message, title=_("Over budget"), indicator="orange")


# ---------------------------------------------------------------- actions
def _load(doctype, name):
	if doctype not in DOCTYPES:
		frappe.throw(_("Approvals are not set up for {0}.").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted or cancelled.").format(name))
	return doc


@frappe.whitelist()
def get_status(doctype, name):
	"""For the form: where the document stands and whether the user may act."""
	doc = _load(doctype, name)
	rows = matrix_rows(doc)
	level, approvers = next_level(doc, rows)
	last = doc.approvals[-1] if doc.approvals else None
	return {
		"required": cint(doc.approval_level_required),
		"reached": cint(doc.approval_level_reached),
		"next_level": level,
		"next_approver": describe(approvers) if level else None,
		"can_act": bool(level) and can_approve(approvers) and not is_own(doc),
		"own_document": is_own(doc),
		"rejected": bool(last and last.action == "Rejected" and not cint(doc.approval_level_reached)),
	}


def is_own(doc):
	return frappe.session.user != "Administrator" and doc.owner == frappe.session.user


@frappe.whitelist()
def approve(doctype, name, comment=None):
	return _act(doctype, name, "Approved", comment)


@frappe.whitelist()
def reject(doctype, name, comment=None):
	if not (comment or "").strip():
		frappe.throw(_("Say why it is rejected, so the requester can put it right."))
	return _act(doctype, name, "Rejected", comment)


def _act(doctype, name, action, comment):
	doc = _load(doctype, name)
	rows = matrix_rows(doc)
	doc.approval_level_required = required_level(doc, rows)
	level, approvers = next_level(doc, rows)
	if not level:
		frappe.throw(_("{0} has every approval it needs.").format(name))
	if is_own(doc):
		frappe.throw(_("You raised {0}, so someone else has to approve it.").format(name))
	if not can_approve(approvers):
		frappe.throw(_("Level {0} of {1} is approved by {2}.").format(level, name, describe(approvers)), frappe.PermissionError)

	doc.append("approvals", {"level": level, "approver": frappe.session.user, "action": action,
	                         "comment": comment, "on": now_datetime()})
	# A rejection sends it back to the start: once corrected, every level approves again.
	doc.approval_level_reached = level if action == "Approved" else 0
	doc.flags.ignore_permissions = True
	doc.save()

	if action == "Approved" and cint(doc.approval_level_reached) >= cint(doc.approval_level_required):
		take_workflow_step(doc, submitting=True)
	elif action == "Rejected":
		take_workflow_step(doc, to_state="Rejected")
	if frappe.db.get_value(doctype, name, "docstatus") == 1:
		return {"submitted": True}
	return get_status(doctype, name)


def take_workflow_step(doc, submitting=False, to_state=None):
	"""If the site has a workflow on this doctype and the user may take the
	matching step from where the document is, take it, so nobody approves twice."""
	if not get_workflow_name(doc.doctype):
		return
	workflow = frappe.get_cached_doc("Workflow", get_workflow_name(doc.doctype))
	submits = {s.state for s in workflow.states if cint(s.doc_status) == 1}
	for t in get_transitions(doc):
		if (submitting and t.next_state in submits) or (to_state and t.next_state == to_state):
			apply_workflow(doc, t.action)
			return
