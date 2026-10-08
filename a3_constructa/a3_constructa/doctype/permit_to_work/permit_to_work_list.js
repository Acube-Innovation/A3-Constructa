// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Permit to Work"] = {
	add_fields: ["status", "valid_to"],
	get_indicator(doc) {
		if (doc.status === "Open" && moment(doc.valid_to).isBefore(moment())) return [__("Expired"), "red", "status,=,Open"];
		return { Open: [__("Open"), "blue", "status,=,Open"], Closed: [__("Closed"), "green", "status,=,Closed"],
		         Cancelled: [__("Cancelled"), "gray", "status,=,Cancelled"] }[doc.status];
	},
};
