# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Job Cost Report - catalogue 13.1: the cost of each job, rolled up a tree.

Project → Cost Head → Work Package → WBS → Cost Code. Per row: original budget
(the WBS allocations), approved changes (variations and transfers in the Budget
Revision Log), revised budget, committed (open purchase-order value not yet
invoiced), actual (expense GL entries and material issued to the job, up to the
as-on date), cost to complete (revised − actual − committed, never below zero,
and nothing where there is no budget: the Cost to Complete report's figure), forecast at completion (actual +
committed + cost to complete), variance (revised − forecast) and % consumed
((actual + committed) ÷ revised).

The figures come from the same three sources as Cost Code Wise Costing, read at
the finest grain (project, WBS, cost code) and only then rolled up, so each level
is exactly its children plus an "Unallocated" row for what was booked at that
level and no lower (on a grouping node, with no cost code, or with no WBS) -
nothing is ever counted twice. The levels come from the data: the cost head is
the top-level cost head of the WBS node's own cost head; the work package is the
nearest Work Package node above it. A level a branch doesn't have is skipped.

The as-on date limits actual cost only, as Cost Code Wise Costing's "To Date"
does; budgets and commitments are as they stand. The report checks its project
totals (and, for one project, its cost-code totals) against Cost Code Wise
Costing run with the same filters, and says whether they agree.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from a3_constructa.api.budget_allocation import CHANGES_OUTSIDE_BOQ

FIGURES = ("original_budget", "budget_changes", "committed", "actual")
LEVELS = ("Project", "Cost Head", "Work Package", "WBS", "Cost Code")
TOLERANCE = 0.05


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = filters.get("company") or frappe.defaults.get_user_default("Company")
	filters.as_on = getdate(filters.get("as_on") or today())
	projects = project_list(filters)
	if not projects:
		return columns(), [], _("No projects for these filters.")
	facts = gather(projects, filters)
	rows = build_tree(projects, facts)
	check = reconcile(projects, rows, facts, filters)
	depth = LEVELS.index(filters.depth) + 1 if filters.get("depth") in LEVELS else len(LEVELS)
	# An Unallocated row sits one level below the row it belongs to.
	rows = [r for r in rows if (r["depth_of"] + 1 if r["level"] == "Unallocated" else LEVELS.index(r["level"])) < depth]
	if frappe.utils.cint(filters.get("hide_zero")):
		rows = [r for r in rows if any(abs(flt(r[f])) >= 0.005 for f in FIGURES)]
	return columns(), rows, check["message"], None, summary(rows, check)


# ---------------------------------------------------------------- sources

def project_list(filters):
	conditions = {"company": filters.company}
	if filters.get("project"):
		conditions["name"] = filters.project
	return frappe.get_list("Project", filters=conditions, fields=["name", "project_name"], order_by="name")


def gather(projects, filters) -> dict:
	"""{(project, wbs, cost_code): {figure: amount}} from the Cost Code Wise Costing sources."""
	names = [p.name for p in projects]
	values = {"projects": names, "company": filters.company, "as_on": filters.as_on, "types": CHANGES_OUTSIDE_BOQ}
	facts = defaultdict(lambda: dict.fromkeys(FIGURES, 0.0))

	def add(rows, figure):
		for r in rows:
			facts[(r.project, r.wbs or None, r.cost_code or None)][figure] += flt(r.amount)

	add(frappe.db.sql("""select alloc.project, alloc.wbs, item.cost_code, sum(item.allocated_amount) amount
		from `tabWBS Allocation Item` item join `tabWBS Allocation` alloc on alloc.name = item.parent
		where alloc.docstatus < 2 and alloc.project in %(projects)s
		group by alloc.project, alloc.wbs, item.cost_code""", values, as_dict=True), "original_budget")
	add(frappe.db.sql("""select log.project, log.wbs, log.cost_code, sum(log.amount) amount from `tabBudget Revision Log` log
		where log.change_type in %(types)s and log.project in %(projects)s
		group by log.project, log.wbs, log.cost_code""", values, as_dict=True), "budget_changes")
	committed = frappe.db.sql("""select po.project, poi.wbs, poi.cost_code,
			sum(poi.base_amount - (poi.billed_amt * ifnull(po.conversion_rate, 1))) amount
		from `tabPurchase Order Item` poi join `tabPurchase Order` po on po.name = poi.parent
		where po.docstatus = 1 and po.project in %(projects)s and po.company = %(company)s
		group by po.project, poi.wbs, poi.cost_code""", values, as_dict=True)
	for r in committed:
		r.amount = max(flt(r.amount), 0)  # a fully billed line commits nothing further; its cost is actual
	add(committed, "committed")
	add(frappe.db.sql("""select gle.project, gle.wbs, gle.cost_code, sum(gle.debit) - sum(gle.credit) amount
		from `tabGL Entry` gle join `tabAccount` acc on acc.name = gle.account and acc.root_type = 'Expense'
		where gle.voucher_type != 'Stock Entry' and gle.is_cancelled = 0 and gle.company = %(company)s
			and gle.project in %(projects)s and gle.posting_date <= %(as_on)s
		group by gle.project, gle.wbs, gle.cost_code""", values, as_dict=True), "actual")
	add(frappe.db.sql("""select sed.project, sed.wbs, sed.cost_code, sum(abs(sle.stock_value_difference)) amount
		from `tabStock Ledger Entry` sle join `tabStock Entry Detail` sed on sed.name = sle.voucher_detail_no
		join `tabStock Entry` se on se.name = sle.voucher_no
		where sle.is_cancelled = 0 and sle.voucher_type = 'Stock Entry' and sle.actual_qty < 0 and se.purpose = 'Material Issue'
			and sed.project in %(projects)s and sle.posting_date <= %(as_on)s
		group by sed.project, sed.wbs, sed.cost_code""", values, as_dict=True), "actual")
	return facts


# ---------------------------------------------------------------- tree

def top_cost_heads() -> dict:
	parents = dict(frappe.db.sql("select name, parent_cost_head from `tabCost Head`"))
	names = dict(frappe.db.sql("select name, cost_head_name from `tabCost Head`"))

	def top(ch):
		seen = set()
		while ch and parents.get(ch) and ch not in seen:
			seen.add(ch)
			ch = parents[ch]
		return ch
	return {ch: top(ch) for ch in parents}, names


def wbs_nodes(project) -> dict:
	return {w.name: w for w in frappe.get_all("WBS", filters={"project": project},
	                                         fields=["name", "wbs_name", "node_type", "parent_wbs", "cost_head", "is_group", "lft", "rgt"])}


def place(wbs, nodes, top, root_names):
	"""Where a fact on `wbs` sits: (cost head, work package, wbs node, booked on a grouping node?)."""
	if not wbs or wbs not in nodes:
		return None
	node = nodes[wbs]
	if wbs in root_names:
		return None if node.is_group else ("", "", wbs, False)  # a one-node job: its WBS straight under the project
	chain = []
	cur = node
	while cur and cur.name not in root_names:
		chain.append(cur)
		cur = nodes.get(cur.parent_wbs)
	ch_source = next((c.cost_head for c in chain if c.cost_head), None)
	cost_head = top.get(ch_source, ch_source) if ch_source else "?"
	package = next((c.name for c in chain[1:] if c.node_type == "Work Package"), None)
	grouping = bool(node.is_group) or node.node_type in ("Cost Head", "Work Package")
	if grouping and node.node_type == "Work Package":
		return (cost_head, wbs, None, True)
	if grouping:
		return (cost_head, package, None, True)
	return (cost_head, package, wbs, False)


def build_tree(projects, facts) -> list[dict]:
	top, ch_names = top_cost_heads()
	rows = {}
	children = defaultdict(list)

	def node(key, parent, level, label, drill, sort, depth_of=None):
		if key not in rows:
			rows[key] = {"key": key, "parent_key": parent, "level": level, "label": label, "drill": drill, "sort": sort,
			             "depth_of": depth_of if depth_of is not None else (LEVELS.index(level) if level in LEVELS else 0),
			             **dict.fromkeys(FIGURES, 0.0), "cost_to_complete": 0.0}
			children[parent].append(key)
		return rows[key]

	by_project = defaultdict(list)
	for (project, wbs, cc), f in facts.items():
		by_project[project].append((wbs, cc, f))
	for p in projects:
		nodes = wbs_nodes(p.name)
		roots = {n for n, w in nodes.items() if not w.parent_wbs or w.parent_wbs not in nodes}
		pkey = f"P|{p.name}"
		node(pkey, None, "Project", f"{p.name} · {p.project_name}", {"project": p.name}, (0, p.name))
		for wbs, cc, f in by_project.get(p.name, []):
			where = place(wbs, nodes, top, roots)
			if where is None:  # no WBS, or the project's root node
				leaf = node(f"PU|{p.name}", pkey, "Unallocated", _("Unallocated: no WBS"),
				            {"project": p.name, "wbs": ["in", sorted(roots)] if wbs else ["is", "not set"]}, (9, ""), 0)
			else:
				cost_head, package, w, grouping = where
				parent = pkey
				subtree = lambda name: [n for n, x in nodes.items() if x.lft >= nodes[name].lft and x.rgt <= nodes[name].rgt]  # noqa: E731
				if cost_head:
					ch_wbs = [n for n, x in nodes.items() if x.cost_head and top.get(x.cost_head, x.cost_head) == cost_head]
					parent = node(f"CH|{p.name}|{cost_head}", pkey, "Cost Head", f"{cost_head} · {ch_names.get(cost_head, '')}" if cost_head != "?" else _("No cost head"),
					              {"project": p.name, "wbs": ["in", sorted(ch_wbs)]}, (1, cost_head))["key"]
				if package:
					parent = node(f"WP|{p.name}|{package}", parent, "Work Package", f"{package} · {nodes[package].wbs_name}",
					              {"project": p.name, "wbs": ["in", subtree(package)]}, (2, nodes[package].lft))["key"]
				if grouping:
					level_of = rows[parent]["level"]
					leaf = node(f"{parent}|U", parent, "Unallocated", _("Unallocated: booked on {0}").format(wbs),
					            {"project": p.name, "wbs": wbs}, (9, ""), LEVELS.index(level_of) if level_of in LEVELS else 0)
				else:
					wkey = node(f"W|{p.name}|{w}", parent, "WBS", f"{w} · {nodes[w].wbs_name}", {"project": p.name, "wbs": w},
					            (3, nodes[w].lft))["key"]
					leaf = node(f"CC|{p.name}|{w}|{cc or ''}", wkey, "Cost Code" if cc else "Unallocated",
					            cc or _("Unallocated: no cost code"), {"project": p.name, "wbs": w, "cost_code": cc or ["is", "not set"]},
					            (4, cc or "~"), 3 if not cc else None)
			for fig in FIGURES:
				leaf[fig] += f[fig]
	# Leaf cost to complete, then everything rolls up from the leaves.
	for r in rows.values():
		if not children.get(r["key"]):
			revised = r["original_budget"] + r["budget_changes"]
			# Nothing budgeted, nothing left to spend: a credit (e.g. freight absorbed into stock) isn't work to do.
			r["cost_to_complete"] = max(revised - r["actual"] - r["committed"], 0.0) if revised > 0 else 0.0

	def roll(key):
		r = rows[key]
		for k in children.get(key, []):
			roll(k)
			for fig in (*FIGURES, "cost_to_complete"):
				r[fig] += rows[k][fig]
	tops = children.get(None, [])
	for k in tops:
		roll(k)
	out = []

	def walk(key, indent):
		r = rows[key]
		revised = r["original_budget"] + r["budget_changes"]
		forecast = r["actual"] + r["committed"] + r["cost_to_complete"]
		consumed = r["actual"] + r["committed"]
		out.append({**r, "indent": indent, "revised_budget": revised, "forecast": forecast, "variance": revised - forecast,
		            "percent_consumed": flt(consumed / revised * 100, 1) if revised else (100.0 if consumed else 0.0),
		            "is_unallocated": r["level"] == "Unallocated"})
		for k in sorted(children.get(key, []), key=lambda k: rows[k]["sort"]):
			walk(k, indent + 1)
	for k in tops:
		walk(k, 0)
	return out


# ---------------------------------------------------------------- agreement

def reconcile(projects, rows, facts, filters) -> dict:
	"""Compare with Cost Code Wise Costing run on the same filters."""
	from a3_constructa.a3_constructa.report.cost_code_wise_costing import cost_code_wise_costing as ccwc

	base = {"company": filters.company, "to_date": filters.as_on}
	if filters.get("project"):
		base["project"] = filters.project
	theirs = {r["grouping"]: r for r in ccwc.execute({**base, "group_by": "Project"})[1]}
	ours = {r["drill"]["project"]: r for r in rows if r["level"] == "Project"}
	pairs = (("original_budget", "original_budget"), ("budget_changes", "budget_changes"), ("committed", "committed"), ("actual", "actual"))
	diffs = []
	for p in projects:
		a, b = ours.get(p.name, {}), theirs.get(p.name, {})
		for mine, other in pairs:
			if abs(flt(a.get(mine)) - flt(b.get(other))) > TOLERANCE:
				diffs.append(_("{0} {1}: {2} here, {3} there").format(p.name, mine.replace("_", " "), flt(a.get(mine), 2), flt(b.get(other), 2)))
	by_code = None
	if filters.get("project"):
		mine = defaultdict(lambda: dict.fromkeys(FIGURES, 0.0))
		for (project, wbs, cc), f in facts.items():
			if cc:
				for fig in FIGURES:
					mine[cc][fig] += f[fig]
		theirs_cc = {r["grouping"]: r for r in ccwc.execute({**base, "group_by": "Cost Code"})[1]}
		for cc in set(mine) | set(theirs_cc):
			for fig, other in pairs:
				if abs(flt(mine[cc][fig]) - flt(theirs_cc.get(cc, {}).get(other))) > TOLERANCE:
					diffs.append(_("{0} {1}: {2} here, {3} there").format(cc, fig.replace("_", " "), flt(mine[cc][fig], 2),
					                                                     flt(theirs_cc.get(cc, {}).get(other), 2)))
		by_code = len(mine)
	ok = not diffs
	scope = _("project totals") + (_(" and the {0} cost codes").format(by_code) if by_code is not None else "")
	message = (_("Agrees with Cost Code Wise Costing for the same filters ({0}): budget, changes, committed and actual.").format(scope) if ok
	           else _("Differs from Cost Code Wise Costing: {0}").format("; ".join(diffs[:6])))
	return {"ok": ok, "diffs": diffs, "message": message}


# ---------------------------------------------------------------- output

def columns():
	cur = {"fieldtype": "Currency", "width": 125}
	return [
		{"fieldname": "label", "label": _("Project / Cost Head / Work Package / WBS / Cost Code"), "fieldtype": "Data", "width": 330},
		{"fieldname": "level", "label": _("Level"), "fieldtype": "Data", "width": 105},
		{"fieldname": "original_budget", "label": _("Original Budget"), **cur},
		{"fieldname": "budget_changes", "label": _("Approved Changes"), **cur},
		{"fieldname": "revised_budget", "label": _("Revised Budget"), **cur},
		{"fieldname": "committed", "label": _("Committed"), **cur},
		{"fieldname": "actual", "label": _("Actual"), **cur},
		{"fieldname": "cost_to_complete", "label": _("Cost to Complete"), **cur},
		{"fieldname": "forecast", "label": _("Forecast at Completion"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "variance", "label": _("Variance"), **cur},
		{"fieldname": "percent_consumed", "label": _("% Consumed"), "fieldtype": "Percent", "width": 100},
	]


def summary(rows, check):
	top = [r for r in rows if r["level"] == "Project"]
	tot = lambda f: sum(flt(r[f]) for r in top)  # noqa: E731
	return [
		{"label": _("Revised budget"), "value": tot("revised_budget"), "datatype": "Currency"},
		{"label": _("Actual + committed"), "value": tot("actual") + tot("committed"), "datatype": "Currency"},
		{"label": _("Forecast at completion"), "value": tot("forecast"), "datatype": "Currency"},
		{"label": _("Variance"), "value": tot("variance"), "datatype": "Currency", "indicator": "Red" if tot("variance") < 0 else "Green"},
		{"label": _("Cost Code Wise Costing"), "value": _("Agrees") if check["ok"] else _("Differs"), "datatype": "Data",
		 "indicator": "Green" if check["ok"] else "Red"},
	]
