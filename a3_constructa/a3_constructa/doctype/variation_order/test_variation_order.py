# Copyright (c) 2026, Acube Innovations Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_constructa.a3_constructa.doctype.awarded_quotation.test_awarded_quotation import make_award


def make_variation(award, items, **values):
	doc = frappe.get_doc(
		{"doctype": "Variation Order", "subject": "_Test variation", "awarded_quotation": award, "items": items}
	)
	doc.update(values)
	return doc.insert()


class TestVariationOrder(FrappeTestCase):
	def test_total_and_fetched_fields(self):
		award = make_award()
		vo = make_variation(award.name, [{"description": "A", "qty": 2, "rate": 10}, {"description": "B", "qty": -1, "rate": 5}])
		self.assertEqual(vo.total_amount, 15)
		self.assertEqual(vo.customer, award.customer)
		self.assertEqual(vo.currency, award.currency)

	def test_omission_must_reduce_the_contract(self):
		award = make_award()
		with self.assertRaises(frappe.ValidationError):
			make_variation(award.name, [{"description": "A", "qty": 1, "rate": 10}], variation_type="Omission")
		vo = make_variation(award.name, [{"description": "A", "qty": -1, "rate": 10}], variation_type="Omission")
		self.assertEqual(vo.total_amount, -10)

	def test_approval_is_dated(self):
		award = make_award()
		vo = make_variation(award.name, [{"description": "A", "qty": 1, "rate": 10}], status="Approved")
		self.assertTrue(vo.approved_date)

	def test_cancelled_award_takes_no_variations(self):
		award = make_award(status="Cancelled")
		with self.assertRaises(frappe.ValidationError):
			make_variation(award.name, [{"description": "A", "qty": 1, "rate": 10}])
