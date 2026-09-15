# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Cost to Complete - build sheet head 72, row 38.

The forecast that matters on a running job: given what has been spent and
committed so far, what will this cost code finish at, and is that above or below
the budget.

Forecast final cost is cost to date plus what is committed but not yet spent
plus what is left to buy. The last term is the honest part - it assumes the
unbought remainder costs what the BOQ said it would, which is the assumption
everyone makes and nobody writes down.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_constructa.a3_constructa.report.cost_code_wise_costing.cost_code_wise_costing import (
	get_actual,
	get_budget,
	get_committed,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Same three sources as Cost Code Wise Costing, so the two reports agree.
	budget = get_budget(filters, "cost_code")
	committed = get_committed(filters, "cost_code")
	actual = get_actual(filters, "cost_code")
	boq = get_boq(filters)

	data = []
	for code in sorted(set(budget) | set(committed) | set(actual) | set(boq)):
		b = flt(budget.get(code)) or flt(boq.get(code, {}).get("amount"))
		spent = flt(actual.get(code))
		commitment = flt(committed.get(code))
		# What is still to be procured, on the BOQ's own rates.
		to_buy = max(b - spent - commitment, 0)
		forecast = spent + commitment + to_buy

		data.append({
			"cost_code": code,
			"description": boq.get(code, {}).get("description"),
			"budget": b,
			"cost_to_date": spent,
			"committed_unspent": commitment,
			"remaining_to_buy": to_buy,
			"forecast_final_cost": forecast,
			"forecast_variance": b - forecast,
			"percent_complete": (spent / b * 100) if b else 0,
		})

	if filters.get("only_adverse"):
		data = [r for r in data if r["forecast_variance"] < 0]

	data.sort(key=lambda r: r["forecast_variance"])
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "cost_code", "label": _("Cost Code"), "fieldtype": "Link",
		 "options": "Cost Code", "width": 150},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data",
		 "width": 200},
		{"fieldname": "budget", "label": _("Budget"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "cost_to_date", "label": _("Cost to Date"), "fieldtype": "Currency",
		 "width": 130},
		{"fieldname": "committed_unspent", "label": _("Committed Unspent"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "remaining_to_buy", "label": _("Remaining to Buy"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "forecast_final_cost", "label": _("Forecast Final Cost"),
		 "fieldtype": "Currency", "width": 160},
		{"fieldname": "forecast_variance", "label": _("Forecast Variance"),
		 "fieldtype": "Currency", "width": 150},
		{"fieldname": "percent_complete", "label": _("% Spent"), "fieldtype": "Percent",
		 "width": 110},
	]


def get_boq(filters):
	"""Approved BOQ value per cost code, and the line description."""
	conditions = ["boq.docstatus < 2", "item.cost_code is not null", "item.cost_code != ''"]
	values = {}
	if filters.get("project"):
		conditions.append("boq.project = %(project)s")
		values["project"] = filters.project
	if filters.get("cost_code"):
		conditions.append("item.cost_code = %(cost_code)s")
		values["cost_code"] = filters.cost_code

	rows = frappe.db.sql(
		"""
		select item.cost_code,
		       sum(case when item.budget_amount > 0 then item.budget_amount
		                else item.amount end) as amount,
		       max(item.description) as description
		from `tabBOQ Item` item
		inner join `tabBOQ` boq on boq.name = item.parent
		where {conditions}
		group by item.cost_code
		""".format(conditions=" and ".join(conditions)),
		values, as_dict=True,
	)
	return {r.cost_code: {"amount": flt(r.amount), "description": r.description} for r in rows}
