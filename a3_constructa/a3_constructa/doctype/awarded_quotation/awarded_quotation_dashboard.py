# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	return {
		"fieldname": "awarded_quotation",
		"transactions": [
			{"label": _("Planning"), "items": ["BOQ"]},
			{"label": _("Orders"), "items": ["Sales Order", "Variation Order"]},
			{"label": _("Change"), "items": ["Change Event"]},
			{"label": _("Delivery"), "items": ["Deliverable"]},
		],
	}
