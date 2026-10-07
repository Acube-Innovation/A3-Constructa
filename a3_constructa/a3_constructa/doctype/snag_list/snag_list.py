# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Snag List - catalogue 6.11: the defects found walking a room or area before handover.

Each item has a trade, a location, a photo, who fixes it (a crew or a supplier)
and by when. It goes Open → Fixed (the trade says it's done) → Verified (checked;
closed_on set). The list counts what's still open (open or fixed), fixed and
verified, and closes when every item is verified. Practical completion is refused
while any item on the project is still open (P-06H, handover).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today

OUTSTANDING = ("Open", "Fixed")


class SnagList(Document):
	def validate(self):
		if self.wbs and frappe.db.get_value("WBS", self.wbs, "project") != self.project:
			frappe.throw(_("WBS {0} is not part of {1}.").format(self.wbs, self.project))
		if frappe.db.get_value("Project", self.project, "practical_completion_date") and self.is_new():
			frappe.msgprint(_("{0} is past practical completion: defects now go on Warranty Claims.").format(self.project),
			                indicator="orange", alert=True)
		for row in self.items:
			if row.due_date and getdate(row.due_date) < getdate(self.inspection_date):
				frappe.throw(_("Snag {0}: due before the inspection date.").format(row.idx))
			if row.responsible and row.responsible_type:
				row.responsible_name = frappe.db.get_value(row.responsible_type, row.responsible,
				                                           "crew_name" if row.responsible_type == "Crew" else "supplier_name")
			else:
				row.responsible_name = None
			if row.status == "Verified":
				row.closed_on = row.closed_on or today()
			else:
				row.closed_on = None
		self.open_count = sum(1 for r in self.items if r.status in OUTSTANDING)
		self.fixed_count = sum(1 for r in self.items if r.status == "Fixed")
		self.closed_count = sum(1 for r in self.items if r.status == "Verified")
		self.status = "Closed" if self.items and not self.open_count else "Open"
		where = " · ".join(x for x in (self.building, self.floor, self.room) if x)
		self.title = f"{frappe.db.get_value('Project', self.project, 'project_name') or self.project}" + (f": {where}" if where else "")


def outstanding(project) -> list[dict]:
	"""Snag items still open or fixed on the project, by list."""
	return frappe.db.sql("""select l.name, l.title, sum(i.status = 'Open') open, sum(i.status = 'Fixed') fixed
		from `tabSnag Item` i join `tabSnag List` l on l.name = i.parent
		where l.project = %s and i.status in ('Open', 'Fixed') group by l.name, l.title order by l.name""", project, as_dict=True)
