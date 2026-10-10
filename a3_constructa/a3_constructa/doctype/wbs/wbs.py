# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet

# Catalogue 1.2: Draft -> Active -> On Hold -> Completed, with On Hold <-> Active.
# An Active node may also be closed straight away; going through On Hold just to
# finish would make every completed node look as if it had been stopped.
ALLOWED_STATUS_MOVES = {
	"Draft": {"Active"},
	"Active": {"On Hold", "Completed"},
	"On Hold": {"Active", "Completed"},
	"Completed": set(),
}
OPENING_STATUSES = {"Draft", "Active"}


class WBS(NestedSet):
	def validate(self):
		self.inherit_from_parent()
		self.validate_parent()
		self.set_wbs_level()
		self.set_node_type()
		self.validate_status_move()
		self.validate_boq_reference()

	def on_update(self):
		super().on_update()
		self.validate_children()

	def set_wbs_level(self):
		"""Build sheet head 4, row 21: wbs_level is auto-set from tree depth.

		A root node is level 1 and each child is one deeper than its parent, so
		the field is read-only on the form and derived here instead. Reading the
		parent's stored level rather than walking to the root keeps this O(1);
		it holds because a parent is always saved before its children.
		"""
		parent = self.get("parent_wbs")
		if not parent:
			self.wbs_level = 1
			return

		self.wbs_level = (frappe.db.get_value("WBS", parent, "wbs_level") or 0) + 1

	def inherit_from_parent(self):
		"""A child left without a project or cost head takes its parent's."""
		if not self.parent_wbs:
			return
		parent = frappe.db.get_value("WBS", self.parent_wbs, ["project", "cost_head"], as_dict=True)
		if parent:
			self.project = self.project or parent.project
			self.cost_head = self.cost_head or parent.cost_head

	def validate_parent(self):
		"""A child belongs to its parent's project and sits inside its parent's cost head.

		Inside means the same cost head or one below it in the Cost Head tree, so
		Architectural works (MSS-AR) can hold a Flooring node (MSS-AR-FL) but not
		an MEP one.
		"""
		if not self.parent_wbs:
			return
		parent = frappe.db.get_value("WBS", self.parent_wbs, ["project", "cost_head"], as_dict=True)
		check_fits_parent(self, parent, self.parent_wbs)

	def validate_children(self):
		"""Changing a parent's project or cost head must not strand its children."""
		if self.is_new() or not (self.has_value_changed("project") or self.has_value_changed("cost_head")):
			return
		for child in frappe.get_all("WBS", filters={"parent_wbs": self.name}, fields=["name", "project", "cost_head"]):
			check_fits_parent(child, self, self.name)

	def set_node_type(self):
		if not self.node_type:
			self.node_type = node_type_from_position(self.is_group, self.parent_wbs, self.cost_head)

	def validate_status_move(self):
		self.status = self.status or "Draft"
		if self.is_new():
			if self.status not in OPENING_STATUSES:
				frappe.throw(_("A new WBS node starts as Draft or Active, not {0}.").format(self.status))
			return

		before = self.get_doc_before_save()
		old = before.status if before else None
		if not old or old == self.status:
			return
		if self.status not in ALLOWED_STATUS_MOVES.get(old, set()):
			allowed = ", ".join(sorted(ALLOWED_STATUS_MOVES.get(old, set()))) or _("nothing; it is final")
			frappe.throw(
				_("WBS {0} cannot move from {1} to {2}. From {1} it can move to: {3}.").format(
					frappe.bold(self.name), old, self.status, allowed
				),
				title=_("Status change not allowed"),
			)

	def validate_boq_reference(self):
		if not self.boq:
			self.boq_item = None
			return
		boq_project = frappe.db.get_value("BOQ", self.boq, "project")
		if self.project and boq_project and boq_project != self.project:
			frappe.throw(_("BOQ {0} belongs to project {1}, not {2}.").format(self.boq, boq_project, self.project))
		if self.boq_item and not frappe.db.exists(
			"BOQ Item", {"name": self.boq_item, "parent": self.boq, "parenttype": "BOQ"}
		):
			frappe.throw(_("BOQ line {0} is not a line of BOQ {1}. Pick it again from the list.").format(self.boq_item, self.boq))


def check_fits_parent(child, parent, parent_name):
	if parent.project and child.project != parent.project:
		frappe.throw(
			_("WBS {0} must be in project {1}, the same as its parent {2}.").format(
				frappe.bold(child.name or child.get("wbs_code")), parent.project, parent_name
			),
			title=_("Parent mismatch"),
		)
	if parent.cost_head and not is_same_or_below(child.cost_head, parent.cost_head):
		frappe.throw(
			_("WBS {0} has cost head {1}, which is not {2} or below it, the cost head of its parent {3}.").format(
				frappe.bold(child.name or child.get("wbs_code")), child.cost_head or _("(none)"), parent.cost_head, parent_name
			),
			title=_("Parent mismatch"),
		)


def is_same_or_below(cost_head, ancestor):
	if not cost_head:
		return False
	if cost_head == ancestor:
		return True
	bounds = frappe.db.get_value("Cost Head", ancestor, ["lft", "rgt"], as_dict=True)
	node = frappe.db.get_value("Cost Head", cost_head, ["lft", "rgt"], as_dict=True)
	return bool(bounds and node and bounds.lft < node.lft and node.rgt < bounds.rgt)


def node_type_from_position(is_group, parent_wbs, cost_head):
	"""Leaves are WBS nodes. A group under a top-level cost head (or with none) is
	a Cost Head node; a group under a sub-head is a Work Package."""
	if not is_group:
		return "WBS"
	if not cost_head or not parent_wbs:
		return "Cost Head"
	if frappe.db.get_value("Cost Head", cost_head, "parent_cost_head"):
		return "Work Package"
	return "Cost Head"


@frappe.whitelist()
def get_boq_lines(boq):
	"""The lines of one BOQ, for the BOQ Line picker on the WBS form."""
	frappe.has_permission("BOQ", "read", boq, throw=True)
	return frappe.get_all(
		"BOQ Item",
		filters={"parent": boq, "parenttype": "BOQ"},
		fields=["name", "idx", "item_code", "item_name", "wbs", "uom", "boq_qty"],
		order_by="idx",
	)
