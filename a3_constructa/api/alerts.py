# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Catalogue 13.6: exception alerts.

Each active Alert Rule names a condition, a threshold, its recipients and a
channel. Once a day (a Weekly rule once a week) the rule finds the records in
that condition, keeps those past the threshold, leaves out any it alerted in
the last 7 days (its Alert Log), and tells the recipients: an in-app
notification per record, and one email listing them, each naming the record
and linking to it.

The records come from the same checks the overview tabs show under "Needs
attention", so an alert and the tab never disagree; the threshold can only
narrow what the tab lists:

- Task slipped: Project Operations, "Critical tasks late" - days the task is
  driving the finish late (critically_late);
- IPC overdue: Sales & Billing, "IPCs not certified after 21 days" - days
  since it went to the client;
- Purchase order late: Procurement, "Purchase orders past their delivery
  date" - days past the date;
- Shipment late: Delivery & Logistics, "Shipments past their expected
  receipt date" - days past the date;
- WBS over budget: nodes whose committed + actual cost is over their budget,
  by the figures the budget check on requests and orders uses (P-09A) - % over;
- Certificate expiring: the certificates P-07B reminds HR of - days to expiry
  (within 30 when the threshold is 0);
- Approval waiting: the Approvals Pending report (requests and orders waiting
  for a level) and BOQs pending approval - days waiting.
"""

from collections import defaultdict
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_datetime, get_url_to_form, getdate, now_datetime, today

RESEND_AFTER_DAYS = 7
UNITS = {"WBS over budget": "%"}


# ---------------------------------------------------------------- sources

def overview_check(module, label):
	overview = frappe.get_attr(f"a3_constructa.api.{module}_overview.get_overview")()
	return next((c for c in overview.get("health") or [] if c.get("label") == _(label)), None)


def check_records(module, label):
	"""The records an overview check counts: its name list, else its filters."""
	c = overview_check(module, label)
	if not c or not c.get("count"):
		return c and c.get("doctype"), []
	names = (c.get("filters") or {}).get("name")
	if isinstance(names, list) and len(names) == 2 and names[0] == "in":
		return c["doctype"], list(names[1])
	# The tab counts with its own scoping (the default company): list with the same.
	mod = frappe.get_module(f"a3_constructa.api.{module}_overview")
	filters = mod._scoped(c["doctype"], c["filters"]) if hasattr(mod, "_scoped") else c["filters"]
	return c["doctype"], frappe.get_all(c["doctype"], filters=filters, pluck="name")


def item(doctype, name, value, detail):
	return {"doctype": doctype, "name": name, "value": flt(value), "detail": detail}


def task_slipped():
	from a3_constructa.api.project_operations_overview import critically_late

	doctype, names = check_records("project_operations", "Critical tasks late")
	now = getdate(today())
	out = []
	for t in frappe.get_all("Task", filters={"name": ["in", names or [""]]},
	                        fields=["name", "subject", "project", "status", "is_milestone", "exp_end_date", "forecast_end", "is_critical",
	                                "total_float_days"]):
		days = critically_late(t, now)
		out.append(item("Task", t.name, days, _("{0} ({1}) is driving the finish {2} days late").format(t.subject, t.project, days)))
	return out


def ipc_overdue():
	doctype, names = check_records("sales_billing", "IPCs not certified after 21 days")
	out = []
	for d in frappe.get_all("Client IPC", filters={"name": ["in", names or [""]]}, fields=["name", "project", "submitted_on", "claimed_amount"]):
		days = date_diff(today(), d.submitted_on) if d.submitted_on else 0
		out.append(item("Client IPC", d.name, days, _("{0} ({1}) with the client {2} days, not certified").format(d.name, d.project, days)))
	return out


def po_late():
	doctype, names = check_records("procurement", "Purchase orders past their delivery date")
	out = []
	for d in frappe.get_all("Purchase Order", filters={"name": ["in", names or [""]]}, fields=["name", "supplier", "schedule_date"]):
		days = date_diff(today(), d.schedule_date) if d.schedule_date else 0
		out.append(item("Purchase Order", d.name, days, _("{0} from {1} is {2} days past its delivery date").format(d.name, d.supplier, days)))
	return out


def shipment_late():
	doctype, names = check_records("delivery_logistics", "Shipments past their expected receipt date")
	out = []
	for d in frappe.get_all("Shipment Tracking", filters={"name": ["in", names or [""]]}, fields=["name", "status", "expected_receipt_date"]):
		days = date_diff(today(), d.expected_receipt_date) if d.expected_receipt_date else 0
		out.append(item("Shipment Tracking", d.name, days, _("{0} ({1}) is {2} days past its expected receipt").format(d.name, _(d.status), days)))
	return out


def wbs_over_budget():
	"""Nodes whose committed + actual cost is over their budget, by the same figures the
	budget check on requests and orders uses (P-09A). A parent over only because a
	child is, is left to the child."""
	from a3_constructa.api.budget_allocation import wbs_budget, wbs_committed_and_actual

	out = []
	projects = frappe.get_all("Project", filters={"status": ["not in", ["Completed", "Cancelled"]]}, pluck="name")
	for project in projects:
		nodes = frappe.get_all("WBS", filters={"project": project}, fields=["name", "wbs_name", "lft", "rgt"], order_by="lft")
		over = {}
		for n in nodes:
			budget = flt(wbs_budget(project, n.name))
			if budget <= 0:
				continue
			committed, actual = wbs_committed_and_actual(project, n.name)
			spent = flt(committed) + flt(actual)
			if spent > budget:
				over[n.name] = (n, budget, spent)
		for name, (n, budget, spent) in over.items():
			if any(o.lft > n.lft and o.rgt < n.rgt for o, *_r in over.values()):
				continue
			pct = (spent - budget) / budget * 100
			out.append(item("WBS", name, pct, _("{0} {1}: committed and spent {2} against a budget of {3} ({4}% over)").format(
				name, n.wbs_name, frappe.format_value(spent, {"fieldtype": "Currency"}), frappe.format_value(budget, {"fieldtype": "Currency"}),
				round(pct, 1))))
	return out


def certificate_expiring(window):
	window = int(window) or 30
	out = []
	for r in frappe.db.sql("""select c.name, c.parent employee, c.certificate_type, c.expiry_date, e.employee_name
		from `tabEmployee Certificate` c join tabEmployee e on e.name = c.parent
		where c.parenttype = 'Employee' and e.status = 'Active' and c.expiry_date >= %(today)s
			and c.expiry_date <= date_add(%(today)s, interval %(window)s day)""", {"today": getdate(today()), "window": window}, as_dict=True):
		days = date_diff(r.expiry_date, today())
		out.append(item("Employee", r.employee, days, _("{0}'s {1} expires in {2} days").format(r.employee_name, _(r.certificate_type).lower(), days))
		           | {"key": r.name})
	return out


def approval_waiting():
	from a3_constructa.a3_constructa.report.approvals_pending import approvals_pending

	out = []
	for r in approvals_pending.execute({})[1]:
		if r.get("is_rejected"):
			continue
		out.append(item(r["document_type"], r["document"], r["age_days"], _("{0} waiting {1} days for {2} ({3})").format(
			r["document"], r["age_days"], r["approver"], r["status"])))
	doctype, names = check_records("planning", "BOQs waiting for approval")
	for b in frappe.get_all("BOQ", filters={"name": ["in", names or [""]]}, fields=["name", "project", "modified"]):
		days = date_diff(today(), b.modified)
		out.append(item("BOQ", b.name, days, _("{0} ({1}) waiting {2} days for approval").format(b.name, b.project, days)))
	return out


SOURCES = {
	"Task slipped": task_slipped,
	"IPC overdue": ipc_overdue,
	"Purchase order late": po_late,
	"Shipment late": shipment_late,
	"WBS over budget": wbs_over_budget,
	"Certificate expiring": None,  # takes the window
	"Approval waiting": approval_waiting,
}


def records(rule) -> list[dict]:
	"""The records in the rule's condition and past its threshold."""
	threshold = flt(rule.threshold)
	if rule.condition == "Certificate expiring":
		return certificate_expiring(threshold)  # the threshold is the window: expiring within it
	found = SOURCES[rule.condition]()
	if rule.condition == "WBS over budget":
		return [i for i in found if i["value"] > threshold]
	return [i for i in found if i["value"] >= threshold]


# ---------------------------------------------------------------- sending

def recipients(rule) -> list[str]:
	users = set()
	for r in rule.recipients:
		if r.recipient_type == "User" and r.user:
			users.add(r.user)
		elif r.recipient_type == "Role" and r.role:
			users.update(frappe.db.sql_list("""select distinct hr.parent from `tabHas Role` hr join tabUser u on u.name = hr.parent
				where hr.role = %s and hr.parenttype = 'User' and u.enabled = 1 and u.user_type = 'System User'
					and u.name not in ('Administrator', 'Guest')""", r.role))
	return sorted(u for u in users if frappe.db.get_value("User", u, "enabled"))


def recently_sent(rule, now) -> set:
	return {(l.reference_doctype, l.reference_name, l.get("detail_key") or "") for l in rule.log
	        if l.sent_on and (get_datetime(now) - get_datetime(l.sent_on)).days < RESEND_AFTER_DAYS}


def run_rule(rule, now=None, send=True) -> dict:
	"""Evaluate one rule; send what is new. Returns what it found and sent."""
	now = now or now_datetime()
	found = records(rule)
	recent = {(d, n) for d, n, _k in recently_sent(rule, now)}
	new = [i for i in found if (i["doctype"], i["name"]) not in recent]
	users = recipients(rule)
	result = {"rule": rule.name, "found": len(found), "new": len(new), "held": len(found) - len(new), "users": users, "items": new}
	if not send:
		return result
	if new and users:
		subject = _("{0}: {1}").format(rule.rule_name, _("{0} to look at").format(len(new)))
		if rule.channel in ("In-app", "Both"):
			for i in new:
				for u in users:
					frappe.get_doc({"doctype": "Notification Log", "for_user": u, "type": "Alert", "document_type": i["doctype"],
					                "document_name": i["name"], "subject": f"{rule.rule_name}: {i['detail']}",
					                "email_content": i["detail"]}).insert(ignore_permissions=True)
		if rule.channel in ("Email", "Both"):
			emails = [e for e in (frappe.db.get_value("User", u, "email") for u in users) if e]
			lines = "".join(f'<li><a href="{get_url_to_form(i["doctype"], i["name"])}">{frappe.utils.escape_html(i["name"])}</a>: '
			                f'{frappe.utils.escape_html(i["detail"])}</li>' for i in new)
			frappe.sendmail(recipients=emails, subject=subject, reference_doctype="Alert Rule", reference_name=rule.name,
			                message=f"<p>{frappe.utils.escape_html(_('Alert rule {0} found:').format(rule.rule_name))}</p><ul>{lines}</ul>")
		for i in new:
			rule.append("log", {"reference_doctype": i["doctype"], "reference_name": i["name"], "detail": i["detail"][:140],
			                    "sent_on": now, "recipients": ", ".join(users)})
	rule.last_run = now
	rule.last_result = _("{0} found; {1} sent to {2} people; {3} already sent in the last {4} days").format(
		result["found"], result["new"] if users else 0, len(users), result["held"], RESEND_AFTER_DAYS)
	rule.flags.ignore_permissions = True
	rule.save()
	return result


def due(rule, now) -> bool:
	if rule.frequency != "Weekly" or not rule.last_run:
		return True
	return (get_datetime(now) - get_datetime(rule.last_run)).days >= 7


def daily():
	"""Scheduled: run every active rule that is due."""
	now = now_datetime()
	out = []
	for name in frappe.get_all("Alert Rule", filters={"is_active": 1}, pluck="name"):
		rule = frappe.get_doc("Alert Rule", name)
		if not due(rule, now):
			continue
		try:
			out.append(run_rule(rule, now))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Alert Rule {name}")
	return out


@frappe.whitelist()
def run_now(rule: str, send: int = 1) -> dict:
	"""Preview (send=0) or run a rule now. It is evaluated as the scheduler does,
	over every record (the overview checks would otherwise see only what the
	caller may read), once the caller is allowed to read (or edit) the rule."""
	doc = frappe.get_doc("Alert Rule", rule)
	doc.check_permission("write" if int(send) else "read")
	with as_scheduler():
		result = run_rule(doc, send=bool(int(send)))
		if int(send):
			frappe.db.commit()
	return result


@contextmanager
def as_scheduler():
	"""Act as Administrator for a moment inside a web request, then give the caller
	back their session exactly: frappe.set_user rewrites the session's sid and data
	in place, which would otherwise log the caller out."""
	session = frappe.local.session
	saved = (session.user, session.sid, session.data, frappe.local.form_dict)
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		session.user, session.sid, session.data = saved[:3]
		frappe.local.form_dict = saved[3]
		frappe.local.cache = {}
		frappe.local.role_permissions = {}
		frappe.local.user_perms = None
