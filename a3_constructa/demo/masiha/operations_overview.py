# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""D-06: the Project Operations overview's cases.

- The committee wing's site is the Provincial Assembly site, and its programme has
  been through the critical path: the rewiring, forecast 13 days past its finish
  with 7 days' float, now moves the wing's finish (with the Administrative
  Centre's frame, 58 days forecast past against 23 days' float).
- Work went on at the committee wing yesterday but no site report was filed.
Everything else the overview shows comes from the earlier stages: NCRs (P-06G),
snags (P-06H), site reports and delays (P-06F), the look-ahead (P-06E).
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, log

WING = "Provincial Assembly committee wing"
WING_SITE = "Provincial Assembly Site"


def run():
	wing = frappe.db.get_value("Project", {"project_name": WING, "company": COMPANY}, "name")
	if frappe.db.exists("Location", WING_SITE):
		frappe.db.set_value("Project", wing, "location", WING_SITE, update_modified=False)
	from a3_constructa.overrides.task import critical_path

	result = critical_path(wing)
	critical = [n for n, r in result.items() if r["critical"]]
	log(f"Operations overview: {wing} on {WING_SITE}; critical path through {len(critical)} task(s)")
