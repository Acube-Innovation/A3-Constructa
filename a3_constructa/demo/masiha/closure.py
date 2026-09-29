# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt
"""Step 21: what is finished is closed, and what is not stays in plain sight.

Closed: the first shipment. Left open on purpose, because they are the point of
the closure step: the second lot on the Spanish order (a remaining commitment),
30 m2 of tiles still in transit, 10 m2 in Rejected Goods, the import invoice on
hold and the local invoice half paid.
"""

import frappe

from a3_constructa.demo.masiha.common import COMPANY, at, comment, log


def run():
	shipment = frappe.db.get_value("Shipment Tracking", {"bl_no": "OSL-VLC-MTD-44812", "docstatus": 1}, "name")
	if shipment and frappe.db.get_value("Shipment Tracking", shipment, "status") != "Closed":
		frappe.db.set_value("Shipment Tracking", shipment, "status", "Closed")
		comment("Shipment Tracking", shipment, "Containers returned, demurrage invoiced and costed, goods received. "
		        "Shipment closed.", "logistics", at(-2, 17))
	log("shipment 1 closed; lot 2, transit shortage, rejected tiles and open invoices left visible")
	frappe.db.commit()
