# Copyright (c) 2026, Acube Innovations Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today


def make_customer(name="_Test Constructa Client"):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name}).insert(ignore_mandatory=True)
	return name


def make_award(**values):
	company = frappe.get_all("Company", pluck="name", limit=1)[0]
	doc = frappe.new_doc("Awarded Quotation")
	doc.update(
		{
			# Stated, not left to the site default, which may be another company's currency.
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"title": "_Test Works",
			"customer": make_customer(),
			"company": company,
			"status": "Awarded",
			"start_date": today(),
			"end_date": add_days(today(), 100),
			"components": [
				{"component": "Civil", "qty": 1, "rate": 600},
				{"component": "MEP", "qty": 2, "rate": 200},
			],
		}
	)
	doc.update(values)
	return doc.insert()


class TestAwardedQuotation(FrappeTestCase):
	def test_contract_value_is_the_sum_of_components(self):
		award = make_award()
		self.assertEqual(award.components[1].amount, 400)
		self.assertEqual(award.contract_value, 1000)
		self.assertEqual(award.revised_contract_value, 1000)

	def test_progress_follows_weightage_of_completed_milestones(self):
		award = make_award(
			milestones=[
				{"milestone": "Substructure", "planned_end": add_days(today(), -5), "actual_end": today(), "weightage": 30},
				{"milestone": "Superstructure", "planned_end": add_days(today(), 30), "weightage": 70},
			]
		)
		self.assertEqual(award.milestones[0].status, "Completed")
		self.assertEqual(award.milestones[0].variance_days, 5)
		self.assertEqual(award.progress_percent, 30)

	def test_progress_falls_back_to_milestone_count(self):
		award = make_award(
			milestones=[
				{"milestone": "A", "planned_end": today(), "actual_end": today()},
				{"milestone": "B", "planned_end": today()},
				{"milestone": "C", "planned_end": today()},
				{"milestone": "D", "planned_end": today()},
			]
		)
		self.assertEqual(award.progress_percent, 25)

	def test_completed_needs_an_actual_end(self):
		with self.assertRaises(frappe.ValidationError):
			make_award(milestones=[{"milestone": "A", "planned_end": today(), "status": "Completed"}])

	def test_weightage_cannot_pass_100(self):
		with self.assertRaises(frappe.ValidationError):
			make_award(
				milestones=[
					{"milestone": "A", "planned_end": today(), "weightage": 60},
					{"milestone": "B", "planned_end": today(), "weightage": 50},
				]
			)

	def test_completion_cannot_precede_start(self):
		with self.assertRaises(frappe.ValidationError):
			make_award(end_date=add_days(today(), -1))

	def test_approved_variations_revise_value_and_completion(self):
		award = make_award()
		vo = frappe.get_doc(
			{
				"doctype": "Variation Order",
				"subject": "_Test extra works",
				"awarded_quotation": award.name,
				"status": "Approved",
				"time_extension_days": 10,
				"items": [{"description": "Extra slab", "qty": 5, "rate": 50}],
			}
		).insert()
		award.reload()
		self.assertEqual(award.approved_variations, 250)
		self.assertEqual(award.revised_contract_value, 1250)
		self.assertEqual(getdate(award.revised_end_date), getdate(add_days(today(), 110)))

		# A pending variation does not count, and deleting the approved one takes it back out.
		vo.status = "Submitted to Client"
		vo.save()
		award.reload()
		self.assertEqual(award.revised_contract_value, 1000)

		vo.status = "Approved"
		vo.save()
		vo.delete()
		award.reload()
		self.assertEqual(award.approved_variations, 0)
		self.assertEqual(getdate(award.revised_end_date), getdate(award.end_date))

	def test_component_boq_links_back_to_the_award(self):
		project = frappe.get_doc({"doctype": "Project", "project_name": "_Test Award Project"}).insert().name
		item = frappe.get_all("Item", pluck="name", limit=1)[0]
		boq = frappe.get_doc(
			{"doctype": "BOQ", "project": project, "boq_date": today(), "items": [{"item_code": item, "boq_qty": 1, "rate": 1}]}
		).insert()

		award = make_award(project=project, components=[{"component": "Civil", "qty": 1, "rate": 10, "boq": boq.name}])
		self.assertEqual(frappe.db.get_value("BOQ", boq.name, "awarded_quotation"), award.name)

		# The same BOQ cannot price a second award.
		with self.assertRaises(frappe.ValidationError):
			make_award(project=project, components=[{"component": "Civil", "qty": 1, "rate": 10, "boq": boq.name}])
