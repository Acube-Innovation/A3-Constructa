# Copyright (c) 2026, Acube Innovations Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from a3_constructa.a3_constructa.doctype.awarded_quotation.test_awarded_quotation import make_award


def make_deliverable(**values):
	doc = frappe.get_doc(
		{
			"doctype": "Deliverable",
			"deliverable": "_Test shop drawings",
			"awarded_quotation": make_award().name,
			"due_date": add_days(today(), 7),
		}
	)
	doc.update(values)
	return doc.insert()


class TestDeliverable(FrappeTestCase):
	def test_submission_and_approval_are_dated(self):
		doc = make_deliverable(status="Approved")
		self.assertEqual(getdate(doc.submitted_date), getdate(today()))
		self.assertEqual(getdate(doc.approved_date), getdate(today()))

	def test_resubmission_is_the_next_revision(self):
		doc = make_deliverable(status="Submitted", submitted_date=add_days(today(), -10))
		doc.status = "Revise and Resubmit"
		doc.save()
		self.assertEqual(doc.revision, 0)

		doc.status = "Submitted"
		doc.save()
		self.assertEqual(doc.revision, 1)
		self.assertEqual(getdate(doc.submitted_date), getdate(today()))

	def test_approval_cannot_precede_submission(self):
		with self.assertRaises(frappe.ValidationError):
			make_deliverable(status="Approved", submitted_date=today(), approved_date=add_days(today(), -1))
