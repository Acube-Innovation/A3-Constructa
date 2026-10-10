# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Drawing Register - catalogue 6.10: one record per revision of a drawing.

The latest revision of a drawing number on a project (by revision date) is the
current one; every earlier revision is marked Superseded and points at the one
that replaced it. A superseded drawing is not issued again: a new transmittal
on it is refused, so site never builds from an old revision.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class DrawingRegister(Document):
	def validate(self):
		self.drawing_no = (self.drawing_no or "").strip().upper()
		self.revision = (self.revision or "").strip().upper()
		self.drawing_ref = f"{self.drawing_no} rev {self.revision}: {self.title}"[:140]
		if getdate(self.revision_date) > getdate(today()):
			frappe.throw(_("The revision date can't be in the future."), title=_("Date"))
		same = frappe.db.get_value("Drawing Register", {"project": self.project, "drawing_no": self.drawing_no, "revision": self.revision,
		                                                "name": ["!=", self.name or ""]}, "name")
		if same:
			frappe.throw(_("{0} revision {1} is already registered as {2}.").format(self.drawing_no, self.revision, same), title=_("Duplicate"))
		before = self.get_doc_before_save()
		if self.status == "Superseded" and not self.superseded_by and not (before and before.status == "Superseded"):
			frappe.throw(_("A drawing becomes Superseded when its next revision is registered."), title=_("Status"))
		was_superseded = (before.status == "Superseded") if before else False
		known = {r.name for r in before.transmittals} if before else set()
		for row in self.transmittals:
			if getdate(row.issued_on) < getdate(self.revision_date):
				frappe.throw(_("Row {0}: issued before the revision date.").format(row.idx), title=_("Transmittals"))
			if was_superseded and row.name not in known:
				frappe.throw(_("{0} revision {1} is superseded by {2}: issue the current revision instead.").format(
					self.drawing_no, self.revision, self.superseded_by), title=_("Superseded"))

	def on_update(self):
		supersede(self.project, self.drawing_no)

	def on_trash(self):
		# Older revisions point here; free them so this revision can be deleted.
		for name in frappe.get_all("Drawing Register", filters={"superseded_by": self.name}, pluck="name"):
			frappe.db.set_value("Drawing Register", name, "superseded_by", None)

	def after_delete(self):
		supersede(self.project, self.drawing_no)


def supersede(project, drawing_no):
	"""The latest revision is current; every other revision is Superseded by it."""
	rows = frappe.get_all("Drawing Register", filters={"project": project, "drawing_no": drawing_no},
	                      fields=["name", "status", "revision_date", "creation"], order_by="revision_date desc, creation desc")
	if not rows:
		return
	latest = rows[0]
	if latest.status == "Superseded":
		frappe.db.set_value("Drawing Register", latest.name, {"status": "For construction", "superseded_by": None})
	for r in rows[1:]:
		frappe.db.set_value("Drawing Register", r.name, {"status": "Superseded", "superseded_by": latest.name})
