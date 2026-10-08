// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["RFI"] = {
	add_fields: ["status", "required_by"],
	get_indicator(doc) {
		if (doc.status === "Open" && moment(doc.required_by).isBefore(moment(), "day")) return [__("Overdue"), "red", "status,=,Open"];
		return { Open: [__("Open"), "orange", "status,=,Open"], Answered: [__("Answered"), "blue", "status,=,Answered"],
		         Closed: [__("Closed"), "green", "status,=,Closed"] }[doc.status];
	},
};
