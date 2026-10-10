// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Equipment Log"] = {
	add_fields: ["is_hired", "breakdown_hours", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 0) return [__("Draft"), "red", "docstatus,=,0"];
		if (doc.docstatus === 2) return [__("Cancelled"), "gray", "docstatus,=,2"];
		if (flt(doc.breakdown_hours)) return [__("Breakdown"), "orange", "breakdown_hours,>,0"];
		return doc.is_hired ? [__("Hired"), "blue", "is_hired,=,1"] : [__("Charged"), "green", "is_hired,=,0"];
	},
};
