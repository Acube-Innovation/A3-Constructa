# Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	return {
		"fieldname": "daily_site_report",
		"transactions": [
			{"label": _("Booked from this report"), "items": ["Timesheet", "Equipment Log", "Stock Entry"]},
		],
	}
