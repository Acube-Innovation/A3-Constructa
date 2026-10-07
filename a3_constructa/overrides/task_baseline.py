# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Baseline variance on a task - catalogue 6.4.

Start variance = actual start (else expected start) - baseline start; finish
variance = actual end (else the completion date, else expected end) - baseline
end. Positive is late. Kept on the task whenever it is saved (a push from a
predecessor included) and when a Schedule Revision sets or restores its baseline.
wbs_variance rolls the tasks up the WBS tree.
"""

from collections import defaultdict

import frappe
from frappe.utils import getdate


def current_dates(task):
	start = task.get("act_start_date") or task.get("exp_start_date")
	end = task.get("act_end_date") or task.get("completed_on") or task.get("exp_end_date")
	return start, end


def set_variance(task, save=False):
	start, end = current_dates(task)
	values = {
		"start_variance_days": (getdate(start) - getdate(task.baseline_start)).days if task.get("baseline_start") and start else None,
		"finish_variance_days": (getdate(end) - getdate(task.baseline_end)).days if task.get("baseline_end") and end else None,
	}
	if save:
		task.db_set(values, update_modified=False)
	else:
		task.update(values)
	return values


def validate(doc, method=None):
	set_variance(doc)


def wbs_variance(project) -> dict:
	"""Per WBS node (its descendants' tasks included): task count, baseline and current
	finish, the largest finish variance, and how many tasks finish late."""
	tasks = frappe.get_all("Task", filters={"project": project, "is_template": 0, "status": ["!=", "Cancelled"], "baseline_end": ["is", "set"]},
	                       fields=["name", "wbs", "baseline_end", "exp_end_date", "act_end_date", "completed_on", "finish_variance_days"])
	nodes = {w.name: w for w in frappe.get_all("WBS", filters={"project": project}, fields=["name", "wbs_name", "parent_wbs", "lft", "rgt"])}
	out = defaultdict(lambda: {"tasks": 0, "baseline_finish": None, "current_finish": None, "worst": None, "late": 0})
	for t in tasks:
		node = t.wbs
		seen = set()
		while node and node in nodes and node not in seen:
			seen.add(node)
			agg = out[node]
			agg["tasks"] += 1
			end = getdate(t.act_end_date or t.completed_on or t.exp_end_date) if (t.act_end_date or t.completed_on or t.exp_end_date) else None
			agg["baseline_finish"] = max(filter(None, [agg["baseline_finish"], getdate(t.baseline_end)]))
			if end:
				agg["current_finish"] = max(filter(None, [agg["current_finish"], end]))
			v = t.finish_variance_days
			if v is not None:
				agg["worst"] = v if agg["worst"] is None else max(agg["worst"], v)
				agg["late"] += 1 if v > 0 else 0
			node = nodes[node].parent_wbs
	for node, agg in out.items():
		agg["finish_change"] = (agg["current_finish"] - agg["baseline_finish"]).days if agg["current_finish"] and agg["baseline_finish"] else None
		agg["wbs_name"] = nodes[node].wbs_name
		agg["lft"] = nodes[node].lft
	return dict(out)
