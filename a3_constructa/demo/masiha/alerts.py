# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""P-13F: exception alerts, one rule per condition, run once.

Each rule has a threshold and recipients that suit it: the PM hears about
critical tasks slipping and approvals waiting, finance and the PM about
budget overruns over 10%, the QS and finance (weekly, by email) about IPCs the
client has sat on for three weeks, HR about certificates expiring within 30
days, the purchase manager about orders a fortnight late, logistics about late
shipments. An old catch-all rule for every late order is kept switched off.
Running them again within 7 days sends nothing new.

Rules that email name the demo's people; a role (which on this site also holds
the restored backup's own account) is used only on in-app rules, so no demo
alert is ever addressed outside the demo.
"""

import frappe

from a3_constructa.demo.masiha.common import exists, log, user

RULES = [
	# name, condition, threshold, recipients [(type, value)], channel, frequency, active
	("Critical tasks slipping", "Task slipped", 0, [("User", "pm")], "Both", "Daily", 1),
	("Budget overruns over 10%", "WBS over budget", 10, [("User", "pm"), ("User", "finance")], "Both", "Daily", 1),
	("IPCs stuck with the client", "IPC overdue", 21, [("User", "qs"), ("User", "finance")], "Email", "Weekly", 1),
	("Certificates expiring within 30 days", "Certificate expiring", 30, [("Role", "HR Manager")], "In-app", "Daily", 1),
	("Orders a fortnight late", "Purchase order late", 14, [("User", "procurement")], "Both", "Daily", 1),
	("Shipments overdue", "Shipment late", 0, [("User", "logistics")], "Both", "Daily", 1),
	("Approvals waiting over 5 days", "Approval waiting", 5, [("User", "pm"), ("Role", "Purchase Manager")], "In-app", "Daily", 1),
	("Every late order (old)", "Purchase order late", 0, [("User", "buyer")], "Email", "Weekly", 0),
]


def run():
	made = 0
	for name, condition, threshold, people, channel, frequency, active in RULES:
		if exists("Alert Rule", name):
			continue
		doc = frappe.get_doc({"doctype": "Alert Rule", "rule_name": name, "condition": condition, "threshold": threshold, "channel": channel,
		                      "frequency": frequency, "is_active": active,
		                      "recipients": [{"recipient_type": t, "user": user(v) if t == "User" else None, "role": v if t == "Role" else None}
		                                     for t, v in people]})
		doc.flags.ignore_permissions = True
		doc.insert()
		made += 1
	for name, people in (("Budget overruns over 10%", [("User", "pm"), ("User", "finance")]),
	                     ("Orders a fortnight late", [("User", "procurement")]), ("Every late order (old)", [("User", "buyer")])):
		doc = frappe.get_doc("Alert Rule", name)
		if any(r.recipient_type == "Role" for r in doc.recipients):  # rules made before this was settled
			doc.set("recipients", [{"recipient_type": t, "user": user(v)} for t, v in people])
			doc.flags.ignore_permissions = True
			doc.save()
	from a3_constructa.api.alerts import daily

	results = daily()
	log(f"alert rules created now: {made}; run: " + "; ".join(f"{r['rule']}: {r['found']} found, {r['new']} sent to {len(r['users'])}" for r in results))
