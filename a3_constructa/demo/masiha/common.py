# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""The Masiha Services SARL demo: names, people and helpers every stage shares.

The story follows the client's own two documents: the Design & Build
BOQ -> WBS -> Item mapping (one porcelain tile code split 600 m2 to the ground
floor and 400 m2 to the first) and the 21-step demonstration flow, from masters
to closure. Every record lives in its own company, so the story never touches
the other companies on the site and can be removed with it.
"""

from contextlib import contextmanager

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import add_days, add_to_date, get_datetime, nowdate

COMPANY = "Masiha Services SARL"
ABBR = "MSS"
CURRENCY = "USD"
COUNTRY = "Congo, The Democratic Republic of the"

PROJECT_NAME = "Mbandaka Administrative Centre"
CUSTOMER = "Gouvernement Provincial de l'Equateur"
AWARD_TITLE = "Mbandaka Administrative Centre - Design & Build"

BUYING_PRICE_LIST = "Masiha Buying (USD)"
SELLING_PRICE_LIST = "Masiha Selling (USD)"

# Everyone who acts in the story. Signing in as them is how the demo shows who
# did what, and the timeline of every document records it the same way.
DEMO_PASSWORD = "Masiha@Demo2026"
PEOPLE = {
	"requester": ("Patrick", "Lokwa", "Site Engineer",
	              ["Stock User", "Constructa Site Engineer", "Projects User"]),
	# Purchase User because a purchase receipt reads the supplier's payable account.
	"stores": ("Chantal", "Mboyo", "Stores Supervisor",
	           ["Stock User", "Stock Manager", "Constructa Store Keeper", "Purchase User"]),
	"pm": ("Didier", "Kasongo", "Project Manager",
	       ["Constructa Project Manager", "Projects Manager", "A3 Constructa Admin", "Stock User", "Purchase User"]),
	# Sales User from P-02B: the QS prices the tenders, so she reads the opportunities.
	"qs": ("Esther", "Ngalula", "Quantity Surveyor",
	       ["Constructa Quantity Surveyor", "Projects User", "Sales User"]),
	"buyer": ("Olivier", "Tshibanda", "Buyer", ["Purchase User", "Stock User"]),
	"procurement": ("Marie", "Kalala", "Procurement Manager", ["Purchase Manager", "Purchase User", "Stock User"]),
	"logistics": ("Samuel", "Ilunga", "Logistics & C&F Officer",
	              ["Stock User", "Stock Manager", "Constructa Store Keeper", "Purchase User"]),
	# Purchase User so finance can read the orders it pays and invoices against.
	"finance": ("Grace", "Mwamba", "Finance Officer", ["Accounts User", "Accounts Manager", "Purchase User"]),
	# P-02A: who chases tenders, from enquiry to quotation.
	"sales": ("Bernadette", "Mbo", "Business Development Manager", ["Sales User", "Sales Manager", "Projects User"]),
	# P-02E: approves a quotation priced below the minimum margin.
	"md": ("Albert", "Nzuzi", "Managing Director", ["A3 Constructa Admin", "Sales Manager", "Sales User", "Projects Manager"]),
}


def user(role_key: str) -> str:
	first, last, _title, _roles = PEOPLE[role_key]
	return f"{first}.{last}@masiha.demo".lower()


def day(offset: int) -> str:
	"""A date relative to today; the story runs over the last five months."""
	return add_days(nowdate(), offset)


def wh(short_name: str) -> str:
	return f"{short_name} - {ABBR}"


def acc(account_name: str) -> str:
	return f"{account_name} - {ABBR}"


def cost_center() -> str:
	return f"Main - {ABBR}"


def project() -> str | None:
	return frappe.db.get_value("Project", {"project_name": PROJECT_NAME, "company": COMPANY}, "name")


def log(message: str):
	print(f"  {message}")


@contextmanager
def as_user(role_key: str):
	"""Act as one of the story's people, so the timeline shows who did it."""
	previous = frappe.session.user
	frappe.set_user(user(role_key))
	try:
		yield
	finally:
		frappe.set_user(previous)


def exists(doctype: str, filters) -> str | None:
	return frappe.db.get_value(doctype, filters, "name")


def insert(values: dict, submit: bool = False):
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert()
	if submit:
		doc.submit()
	return doc


def at(offset: int, hour: int = 10, minute: int = 0):
	"""A moment on a story day, for the timestamps the timeline shows."""
	return get_datetime(f"{day(offset)} {hour:02d}:{minute:02d}:00")


def comment(doctype: str, name: str, text: str, by: str | None = None, when=None):
	"""A comment on a document's timeline, as one of the story's people, on a story day."""
	doc = frappe.get_doc(doctype, name)
	c = doc.add_comment("Comment", text, comment_email=user(by) if by else None,
	                    comment_by=" ".join(PEOPLE[by][:2]) if by else None)
	values = {}
	if by:
		values["owner"] = user(by)
	if when:
		values.update({"creation": when, "modified": when})
	if values:
		frappe.db.set_value("Comment", c.name, values, update_modified=False)
	return c


def transition(doctype: str, name: str, action: str, by: str, when, note: str | None = None):
	"""Take a workflow action as one of the story's people, dated on the story day.

	The workflow writes its own timeline entry ("Approved", "Rejected"...); that
	entry is moved to the story day, and the person's reason follows it.

	A request or order is approved level by level first (P-09A); the last level
	may already take the workflow's approving step, in which case it is not taken
	twice.
	"""
	doc = None
	if action == "Approve" and doctype in ("Material Request", "Purchase Order"):
		doc = approve_levels(doctype, name, when, exclude=by)
	if not (doc and doc.docstatus == 1):
		with as_user(by):
			doc = apply_workflow(frappe.get_doc(doctype, name), action)
	latest = frappe.get_all(
		"Comment",
		filters={"reference_doctype": doctype, "reference_name": name, "comment_type": "Workflow"},
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	if latest:
		frappe.db.set_value("Comment", latest[0], {"creation": when, "modified": when}, update_modified=False)
	if note:
		comment(doctype, name, note, by, add_to_date(when, minutes=2))
	return frappe.get_doc(doctype, name)


def assign(doctype: str, name: str, to: str, by: str, when, description: str):
	"""Hand a document to someone (Assign To), as the assigner, on a story day."""
	from frappe.desk.form.assign_to import add

	with as_user(by):
		add({"assign_to": [user(to)], "doctype": doctype, "name": name, "description": description,
		     "date": day(0)})
	todo = frappe.get_all("ToDo", filters={"reference_type": doctype, "reference_name": name,
	                                       "allocated_to": user(to)}, order_by="creation desc", limit=1, pluck="name")
	if todo:
		frappe.db.set_value("ToDo", todo[0], {"creation": when, "modified": when}, update_modified=False)


def approver_for(approvers, owner, exclude=None):
	"""The story's person who gives an approval level: its named user, or someone
	holding its role, never the person who raised the document."""
	for a in approvers:
		if a.approver_user and a.approver_user != owner:
			return next((k for k in PEOPLE if user(k) == a.approver_user), None)
	candidates = [k for k, (_f, _l, _t, roles) in PEOPLE.items() if user(k) != owner]
	if exclude in candidates:  # prefer the person taking the workflow step
		candidates.insert(0, candidates.pop(candidates.index(exclude)))
	for a in approvers:
		for key in candidates:
			if a.approver_role in PEOPLE[key][3]:
				return key
	return None


def approve_levels(doctype: str, name: str, when, exclude=None, upto=None, note=None):
	"""Approve a request or order level by level through the Approval Matrix, as the
	story's people, dated on the story day. Stops at `upto` if given."""
	from a3_constructa.overrides.approvals import approve, matrix_rows, next_level

	doc = frappe.get_doc(doctype, name)
	while doc.docstatus == 0:
		doc.approval_level_required = doc.approval_level_required or 0
		level, approvers = next_level(doc, matrix_rows(doc))
		if not level or (upto and level > upto):
			break
		key = approver_for(approvers, doc.owner, exclude)
		if not key:
			break
		with as_user(key):
			approve(doctype, name, note)
		row = frappe.get_all("Approval Log", filters={"parent": name, "parenttype": doctype, "level": level},
		                     order_by="idx desc", limit=1, pluck="name")
		if row:
			frappe.db.set_value("Approval Log", row[0], "on", when, update_modified=False)
		doc = frappe.get_doc(doctype, name)
	return doc
