# Copyright (c) 2026, Acube Innovations Pvt Ltd and Contributors
# See license.txt
"""BOQ lines followed through Material Request, Purchase Order and Purchase Receipt."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.stock.doctype.material_request.material_request import make_purchase_order
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from a3_constructa.api.award_procurement import get_award_procurement
from a3_constructa.api.boq_procurement import approved_boqs, boq_lines, coverage, get_request_lines


def company():
	return frappe.get_all("Company", filters={"name": ["not like", "%Demo%"]}, pluck="name", order_by="creation")[0]


def stock_items(count=2):
	return frappe.get_all("Item", filters={"is_stock_item": 1, "disabled": 0, "has_variants": 0}, pluck="name", limit=count, order_by="name")


def warehouse(for_company):
	return frappe.get_all("Warehouse", filters={"company": for_company, "is_group": 0}, pluck="name", limit=1)[0]


def supplier(for_company):
	"""A supplier billing in the company's own currency, so amounts compare one to one."""
	name = "_Test BOQ Procurement Supplier"
	if not frappe.db.exists("Supplier", name):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": "All Supplier Groups",
		                "default_currency": frappe.get_cached_value("Company", for_company, "default_currency")}).insert()
	return name


class TestBOQProcurement(FrappeTestCase):
	def setUp(self):
		self.company = company()
		self.warehouse = warehouse(self.company)
		self.items = stock_items()
		self.project = frappe.get_doc(
			# Each test rolls back only at the end of the class, so names must not repeat.
			{"doctype": "Project", "project_name": f"_Test BOQ Procurement {frappe.generate_hash(length=6)}", "company": self.company}
		).insert().name
		self.boq = frappe.get_doc(
			{
				"doctype": "BOQ",
				"project": self.project,
				"boq_date": today(),
				"items": [
					{"item_code": self.items[0], "boq_qty": 100, "rate": 10, "approved_qty": 100, "approved_rate": 10},
					{"item_code": self.items[1], "boq_qty": 50, "rate": 20, "approved_qty": 50, "approved_rate": 20},
				],
			}
		).insert()
		self.boq.submit()

	def request(self, quantities, submit=True):
		"""A Material Request built the way Get Items From > BOQ builds it."""
		lines = {line["item_code"]: line for line in get_request_lines(project=self.project, company=self.company)}
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Purchase",
				"company": self.company,
				"schedule_date": add_days(today(), 7),
				"items": [
					{
						"item_code": item,
						"qty": qty,
						"uom": lines[item]["uom"],
						"conversion_factor": lines[item]["conversion_factor"],
						"schedule_date": add_days(today(), 7),
						"warehouse": self.warehouse,
						"project": self.project,
						"boq": lines[item]["boq"],
						"boq_item": lines[item]["boq_item"],
					}
					for item, qty in quantities.items()
				],
			}
		).insert()
		if submit:
			mr.submit()
		return mr

	def line(self, item):
		return next(line for line in boq_lines([self.boq.name]) if line["item_code"] == item)

	def test_request_lines_offer_what_is_left(self):
		first, second = self.items
		self.request({first: 60})
		self.request({first: 15}, submit=False)
		line = self.line(first)
		self.assertEqual(line["requested_qty"], 60)
		self.assertEqual(line["draft_qty"], 15)
		self.assertEqual(line["to_request"], 25)
		self.assertEqual(self.line(second)["to_request"], 50)

	def test_trace_through_order_and_receipt(self):
		first, second = self.items
		mr = self.request({first: 60, second: 50})

		po = make_purchase_order(mr.name)
		po.supplier = supplier(self.company)
		po.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		po.conversion_rate = 1
		for row in po.items:
			row.rate = 5
		po.insert()
		po.submit()

		pr = make_purchase_receipt(po.name)
		for row in pr.items:
			if row.item_code == first:
				row.qty = row.received_qty = 20
		pr.items = [row for row in pr.items if row.item_code == first]
		pr.insert()
		pr.submit()

		line = self.line(first)
		self.assertEqual((line["requested_qty"], line["ordered_qty"], line["received_qty"]), (60, 60, 20))
		self.assertEqual((line["to_request"], line["to_order"], line["to_receive"]), (40, 0, 40))
		self.assertEqual(line["committed_amount"], 300)

		# Budget-weighted: 1000 of the first line and 1000 of the second.
		totals = coverage(boq_lines([self.boq.name]))
		self.assertEqual(totals["budget"], 2000)
		self.assertEqual(totals["requested"], 80.0)  # (0.6 * 1000 + 1.0 * 1000) / 2000
		self.assertEqual(totals["ordered"], 80.0)
		self.assertEqual(totals["received"], 10.0)  # 0.2 * 1000 / 2000

	def test_request_line_must_match_its_boq_line(self):
		first, second = self.items
		mr = self.request({first: 10}, submit=False)
		mr.items[0].item_code = second
		with self.assertRaises(frappe.ValidationError):
			mr.save()

	def test_unapproved_boq_cannot_be_requested(self):
		draft = frappe.get_doc(
			{
				"doctype": "BOQ",
				"project": self.project,
				"boq_date": today(),
				"items": [{"item_code": self.items[0], "boq_qty": 5, "rate": 1}],
			}
		).insert()
		self.assertNotIn(draft.name, approved_boqs(project=self.project))
		mr = self.request({self.items[0]: 1}, submit=False)
		mr.items[0].boq = draft.name
		mr.items[0].boq_item = draft.items[0].name
		with self.assertRaises(frappe.ValidationError):
			mr.save()

	def test_asking_for_more_than_the_boq_warns_but_saves(self):
		frappe.clear_messages()
		mr = self.request({self.items[1]: 70}, submit=False)
		self.assertTrue(mr.name)
		self.assertTrue(any("More than the BOQ approved" in str(m) for m in frappe.message_log))

	def test_award_page_follows_the_boqs_of_its_award(self):
		award = frappe.get_doc(
			{
				"doctype": "Awarded Quotation",
				"title": "_Test procured works",
				"customer": frappe.get_all("Customer", pluck="name", limit=1)[0],
				"company": self.company,
				"project": self.project,
				"status": "In Progress",
				"components": [{"component": "Civil", "qty": 1, "rate": 2000, "boq": self.boq.name}],
			}
		).insert()
		self.request({self.items[0]: 100})

		data = get_award_procurement(award.name)
		self.assertEqual(data["award"]["lines"], 2)
		self.assertEqual(data["award"]["requested"], 50.0)
		# One package (the BOQ), naming the client line it prices.
		self.assertEqual([c["components"] for c in data["components"]], ["Civil"])
		self.assertEqual(data["document_counts"]["requests"], 1)
		self.assertEqual(len(data["pending"]), 2)
