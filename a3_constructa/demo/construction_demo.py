# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Build and remove the A3 Constructa demo.

    bench --site <site> execute a3_constructa.demo.construction_demo.run
    bench --site <site> execute a3_constructa.demo.construction_demo.teardown

`run` is idempotent: it creates what is missing and leaves what is there, so it
can be re-run after a failure without doubling anything up.
"""

import frappe

from a3_constructa.demo.common import PREFIX, PROJECT_NAME, log

STAGES = [
	("masters", "a3_constructa.demo.masters.run"),
	("planning", "a3_constructa.demo.planning.run"),
	("procurement", "a3_constructa.demo.procurement.run"),
	("logistics", "a3_constructa.demo.logistics.run"),
	("inventory", "a3_constructa.demo.inventory.run"),
	("plant", "a3_constructa.demo.plant.run"),
	("people", "a3_constructa.demo.people.run"),
	("finance", "a3_constructa.demo.finance.run"),
	# Last, because it fills the gaps the main story leaves.
	("extras", "a3_constructa.demo.extras.run"),
]


def run(stage: str | None = None):
	"""Build the demo, or one named stage of it."""
	frappe.flags.mute_emails = True

	for name, method in STAGES:
		if stage and stage != name:
			continue
		print("\n=== %s ===" % name)
		try:
			frappe.get_attr(method)()
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback()
			print("  !! %s failed: %s" % (name, exc))
			raise

	print("\nDemo ready: %s" % PROJECT_NAME)


# ------------------------------------------------------------------- teardown
# Transactions are removed newest-first so that a document is never deleted
# while something still points at it.
TRANSACTION_DOCTYPES = [
	# Salary Slip before Timesheet, and both before Salary Structure: a slip
	# holds the timesheet it costed, and the structure holds the assignments.
	"Salary Slip", "Salary Structure Assignment",
	"Payment Entry", "Journal Entry", "Sales Invoice", "Purchase Invoice",
	"Landed Cost Voucher", "Work Certificate", "Tool Issue", "Asset Repair",
	"Asset Movement", "Asset", "Expense Claim", "Timesheet", "Attendance",
	"Stock Entry", "Purchase Receipt", "Shipment Tracking", "Purchase Order",
	"Supplier Quotation", "Request for Quotation", "Material Request",
	"Procurement Plan", "WBS Allocation", "BOQ",
]

MASTER_DOCTYPES = [
	("Salary Structure", {"name": ["like", PREFIX + "%"]}),
	("Salary Component", {"name": ["in", ["Site Wages"]]}),
	("Asset Spare Part", {}),
	("Freight Rate Contract", {}),
	("Service Route", {"name": ["like", "%Matadi%"]}),
	("Port", {"name": ["in", ["Shanghai", "Matadi"]]}),
	("Cost Code", {"name": ["like", PREFIX + "%"]}),
	("WBS", {"name": ["like", PREFIX + "%"]}),
	("Cost Head", {"name": ["like", PREFIX + "%"]}),
	("Item", {"name": ["like", PREFIX + "%"]}),
	("Warehouse", {"name": ["like", PREFIX + "%"]}),
	("Supplier", {"name": ["like", "MBK%"]}),
	("Supplier", {"name": ["in", ["Congo River Lines", "Matadi Clearing Agents"]]}),
]


def teardown():
	"""Remove the demo. Leaves the app's own masters and anything a user added.

	Reports honestly at the end: ERPNext refuses to delete some records while
	anything still points at them, and saying "removed" when four warehouses are
	still there would be worse than useless.
	"""
	frappe.flags.mute_emails = True
	project = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")

	_release_assets()

	for doctype in TRANSACTION_DOCTYPES:
		_delete_transactions(doctype, project)

	for doctype, filters in MASTER_DOCTYPES:
		_delete_masters(doctype, filters)

	for name in frappe.get_all("Employee", pluck="name"):
		if frappe.db.get_value("Employee", name, "employee_name") in DEMO_EMPLOYEES:
			_force_delete("Employee", name)

	if project:
		_force_delete("Project", project)

	frappe.db.commit()
	_report_residue(project)


def _release_assets():
	"""Put demo assets back into a state that can be cancelled.

	An asset sitting in "Issue" or with an open repair against it cannot be
	cancelled, and the demo deliberately puts two of them there.
	"""
	for name in frappe.get_all("Asset", pluck="name"):
		if frappe.db.get_value("Asset", name, "status") in ("Issue", "Out of Order",
		                                                    "In Maintenance"):
			frappe.db.set_value("Asset", name, "status", "Submitted", update_modified=False)

	for doctype in ("Asset Movement", "Asset Repair", "Asset Maintenance Log"):
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, pluck="name"):
			_force_delete(doctype, name)
	frappe.db.commit()


def _report_residue(project):
	"""Say what is actually left, rather than claiming a clean sweep."""
	leftovers = []
	for doctype in TRANSACTION_DOCTYPES + ["Warehouse", "Serial No"]:
		if not frappe.db.exists("DocType", doctype):
			continue
		count = _demo_count(doctype, project)
		if count:
			leftovers.append("%s x%d" % (doctype, count))

	if leftovers:
		print("\nDemo removed, except: %s" % ", ".join(leftovers))
		print("These are held by stock ledger entries or links ERPNext will not")
		print("break. A site kept for demos can leave them; to clear them")
		print("completely, drop the site and reinstall.")
	else:
		print("\nDemo removed.")


def _demo_count(doctype, project):
	meta = frappe.get_meta(doctype)
	if meta.get_field("item_code"):
		return frappe.db.count(doctype, {"item_code": ["like", "%" + PREFIX + "%"]})
	if project and meta.get_field("project"):
		return frappe.db.count(doctype, {"project": project})
	return frappe.db.count(doctype, {"name": ["like", "%" + PREFIX + "%"]})


DEMO_EMPLOYEES = {"Jean Mukendi", "Alice Kabeya", "Paul Ilunga", "Grace Mbuyi"}


def _delete_transactions(doctype, project):
	if not frappe.db.exists("DocType", doctype):
		return

	meta = frappe.get_meta(doctype)
	names = set()

	if project and meta.get_field("project"):
		names.update(frappe.get_all(doctype, filters={"project": project}, pluck="name"))

	# The demo naming prefix, for anything named after it.
	names.update(frappe.get_all(doctype, filters={"name": ["like", "%" + PREFIX + "%"]},
	                            pluck="name"))

	# Assets are named from their category (HEQ-0001), so neither the project
	# nor the prefix finds them once the project is gone; their item does.
	if meta.get_field("item_code"):
		names.update(frappe.get_all(
			doctype, filters={"item_code": ["like", "%" + PREFIX + "%"]}, pluck="name"))

	# Several transactions carry no project at all - opening stock is the
	# obvious one - and are only findable through the demo items or warehouses
	# on their lines. Missing these is what leaves stock ledger entries behind
	# and makes the demo warehouses undeletable.
	child = _line_doctype(doctype)
	if child:
		for field in ("item_code", "s_warehouse", "t_warehouse", "warehouse"):
			if not frappe.get_meta(child).get_field(field):
				continue
			names.update(frappe.get_all(
				child, filters={field: ["like", "%" + PREFIX + "%"]},
				pluck="parent", parent_doctype=doctype))

	for name in sorted(names):
		_force_delete(doctype, name)
	if names:
		log("removed %d x %s" % (len(names), doctype))


# Where a transaction hides its item and warehouse references.
LINE_DOCTYPES = {
	"Stock Entry": "Stock Entry Detail",
	"Purchase Receipt": "Purchase Receipt Item",
	"Purchase Invoice": "Purchase Invoice Item",
	"Purchase Order": "Purchase Order Item",
	"Material Request": "Material Request Item",
	"Supplier Quotation": "Supplier Quotation Item",
	"Sales Invoice": "Sales Invoice Item",
	"Tool Issue": "Tool Issue Item",
	"Work Certificate": "Work Certificate Item",
}


def _line_doctype(doctype):
	child = LINE_DOCTYPES.get(doctype)
	return child if child and frappe.db.exists("DocType", child) else None


def _delete_masters(doctype, filters):
	if not frappe.db.exists("DocType", doctype):
		return
	for name in frappe.get_all(doctype, filters=filters, pluck="name"):
		_force_delete(doctype, name)


def _force_delete(doctype, name):
	try:
		doc = frappe.get_doc(doctype, name)
		if doc.meta.is_submittable and doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc(doctype, name, force=1, ignore_permissions=True,
		                  delete_permanently=True)
	except Exception as exc:
		# A record something else still links to is left behind rather than
		# breaking the rest of the teardown; re-running clears it.
		print("  left %s %s (%s)" % (doctype, name, str(exc)[:60]))
