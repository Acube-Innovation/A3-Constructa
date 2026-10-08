// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Site Incident"] = {
	add_fields: ["status", "severity"],
	get_indicator(doc) {
		const color = { Open: "red", "Under investigation": "orange", Closed: "green" }[doc.status];
		return [__(doc.status), color, `status,=,${doc.status}`];
	},
};
