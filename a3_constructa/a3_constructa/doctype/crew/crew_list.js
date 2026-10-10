// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Crew"] = {
	add_fields: ["is_active", "headcount", "daily_cost"],
	get_indicator(doc) {
		return doc.is_active ? [__("Active"), "green", "is_active,=,1"] : [__("Disbanded"), "gray", "is_active,=,0"];
	},
};
