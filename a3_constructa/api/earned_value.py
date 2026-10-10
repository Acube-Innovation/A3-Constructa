# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 13.3: earned value per WBS and project, on any date.

- BAC, budget at completion: the WBS node's revised budget (wbs_budget: the
  Budget Revision Log and submitted allocations, so approved variations and
  transfers are in it).
- PV, planned value: BAC × the % the baseline dates plan for the date
  (planned_percent, linear between each task's baseline start and finish).
- EV, earned value: BAC × the WBS % complete on the date. % complete is the
  P-06D roll-up (budget-weighted up the tree, tasks weighted by duration),
  fed with each task's progress *as it stood on the date*:
    · a task measured by quantity: its progress log up to the date ÷ planned qty;
    · a task completed on or before the date: 100;
    · a task whose % is typed (Manual): the value it had on the date, from the
      task's version history; with no history, its % counts from the day the
      task was last changed.
- AC, actual cost: expense ledger entries and material issued to the WBS up to
  the date, the same figures as the Job Cost Report and Cost Code Wise Costing.
  Cost booked to the project with no WBS counts on the project, not on a node.

SV = EV − PV, CV = EV − AC, SPI = EV ÷ PV, CPI = EV ÷ AC, EAC = BAC ÷ CPI and
VAC = BAC − EAC (blank while there is no ratio to take).
"""

import json
from bisect import bisect_right
from collections import defaultdict

import frappe
from frappe.utils import flt, getdate, today

from a3_constructa.api.budget_allocation import wbs_budget
from a3_constructa.overrides.task_progress import DONE, planned_percent, rollup


class Project:
	"""Everything one project's earned value needs, loaded once and read for any date."""

	def __init__(self, project):
		self.project = project
		self.nodes = {w.name: w for w in frappe.get_all("WBS", filters={"project": project},
		                                                fields=["name", "wbs_name", "parent_wbs", "lft", "rgt", "is_group"], order_by="lft")}
		self.tasks = frappe.get_all(
			"Task",
			filters={"project": project, "is_template": 0, "is_group": 0, "status": ["!=", "Cancelled"], "is_milestone": 0, "wbs": ["is", "set"]},
			fields=["name", "wbs", "progress", "status", "progress_method", "planned_qty", "completed_on", "act_end_date",
			        "exp_start_date", "exp_end_date", "baseline_start", "baseline_end", "modified", "creation"],
		)
		self.budget = {n: flt(wbs_budget(project, n)) for n in self.nodes}
		self.logs = defaultdict(list)  # task -> [(date, cumulative qty)]
		for row in frappe.get_all("Task Progress Log", filters={"parenttype": "Task", "parent": ["in", [t.name for t in self.tasks] or [""]]},
		                          fields=["parent", "date", "qty_done"], order_by="date asc, idx asc"):
			series = self.logs[row.parent]
			series.append((getdate(row.date), (series[-1][1] if series else 0) + flt(row.qty_done)))
		self.history = self._manual_history()
		self.costs = self._actual_by_day()

	# ------------------------------------------------------------ progress
	def _manual_history(self):
		"""Typed % per task over time: [(date, %)] from the task's versions."""
		manual = [t.name for t in self.tasks if (t.progress_method or "Manual") == "Manual"]
		history = defaultdict(list)
		if not manual:
			return history
		for v in frappe.get_all("Version", filters={"ref_doctype": "Task", "docname": ["in", manual]},
		                        fields=["docname", "data", "creation"], order_by="creation asc"):
			try:
				changed = json.loads(v.data or "{}").get("changed") or []
			except ValueError:
				continue
			for field, old, new in changed:
				if field == "progress":
					if not history[v.docname]:
						history[v.docname].append((None, flt(old)))  # what it was before the first recorded change
					history[v.docname].append((getdate(v.creation), flt(new)))
		return history

	def progress_on(self, t, day) -> float:
		done_on = t.completed_on or (t.act_end_date if t.status in DONE else None)
		if t.status in DONE and done_on and getdate(done_on) <= day:
			return 100.0
		if (t.progress_method or "Manual") == "Quantity" and flt(t.planned_qty):
			series = self.logs.get(t.name) or []
			i = bisect_right([d for d, _ in series], day)
			return min(100.0, series[i - 1][1] / flt(t.planned_qty) * 100) if i else 0.0
		if (t.progress_method or "Manual") == "Quantity":
			return 0.0
		history = self.history.get(t.name)
		if history:
			value = history[0][1]
			for d, v in history[1:]:
				if d <= day:
					value = v
			return value
		# No recorded change: the % has stood since the task was last changed.
		return flt(t.progress) if getdate(t.modified) <= day else 0.0

	# ------------------------------------------------------------ cost
	def _actual_by_day(self):
		"""{wbs or None: [(date, cumulative amount)]}: the Job Cost Report's actual, by day."""
		rows = frappe.db.sql(
			"""
			select wbs, posting_date, sum(amount) amount from (
				select gle.wbs, gle.posting_date, gle.debit - gle.credit amount
				from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account and acc.root_type = 'Expense'
				where gle.voucher_type != 'Stock Entry' and gle.is_cancelled = 0 and gle.project = %(project)s
				union all
				select sed.wbs, sle.posting_date, abs(sle.stock_value_difference)
				from `tabStock Ledger Entry` sle join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
				join `tabStock Entry` se on se.name = sle.voucher_no
				where sle.is_cancelled = 0 and sle.voucher_type = 'Stock Entry' and sle.actual_qty < 0
					and se.purpose = 'Material Issue' and sed.project = %(project)s
			) costs group by wbs, posting_date order by posting_date
			""",
			{"project": self.project},
			as_dict=True,
		)
		series = defaultdict(list)
		for r in rows:
			key = r.wbs if r.wbs in self.nodes else None
			s = series[key]
			s.append((getdate(r.posting_date), (s[-1][1] if s else 0) + flt(r.amount)))
		return series

	def actual_on(self, key, day) -> float:
		s = self.costs.get(key) or []
		i = bisect_right([d for d, _ in s], day)
		return s[i - 1][1] if i else 0.0

	# ------------------------------------------------------------ figures
	def on(self, day) -> dict:
		"""{wbs: {bac, planned, percent, pv, ev, ac}} plus "" for the project total, on `day`."""
		day = getdate(day)
		own = {}
		for t in self.tasks:
			days = ((getdate(t.exp_end_date) - getdate(t.exp_start_date)).days + 1) if t.exp_start_date and t.exp_end_date else 1
			agg = own.setdefault(t.wbs, {"w": 0.0, "done": 0.0, "plan": 0.0})
			agg["w"] += days
			agg["done"] += days * self.progress_on(t, day)
			agg["plan"] += days * planned_percent(t, day)
		rolled = rollup(self.nodes, own, self.budget) if self.nodes else {}
		own_ac = {n: self.actual_on(n, day) for n in self.nodes}
		out = {}
		for name, r in rolled.items():
			node = self.nodes[name]
			ac = sum(own_ac[n] for n, w in self.nodes.items() if node.lft <= w.lft and w.rgt <= node.rgt)
			out[name] = figures(r["budget"], r["planned"], r["percent"], ac)
		roots = [n for n, w in self.nodes.items() if w.parent_wbs not in self.nodes]
		bac = sum(self.budget[n] for n in roots)
		pv = sum(out[n]["pv"] for n in roots)
		ev = sum(out[n]["ev"] for n in roots)
		ac = sum(out[n]["ac"] for n in roots) + self.actual_on(None, day)
		total = figures(bac, pv / bac * 100 if bac else 0, ev / bac * 100 if bac else 0, ac)
		total["no_wbs_ac"] = self.actual_on(None, day)
		out[""] = total
		return out

	def first_day(self):
		dates = [getdate(d) for t in self.tasks for d in (t.baseline_start or t.exp_start_date,) if d]
		dates += [s[0][0] for s in self.costs.values() if s]
		return min(dates) if dates else getdate(today())


def figures(bac, planned, percent, ac) -> dict:
	pv, ev = bac * planned / 100, bac * percent / 100
	spi = ev / pv if pv else None
	cpi = ev / ac if ac else None
	eac = bac / cpi if cpi else None
	return {"bac": bac, "planned": planned, "percent": percent, "pv": pv, "ev": ev, "ac": ac,
	        "sv": ev - pv, "cv": ev - ac, "spi": spi, "cpi": cpi, "eac": eac, "vac": bac - eac if eac is not None else None}
