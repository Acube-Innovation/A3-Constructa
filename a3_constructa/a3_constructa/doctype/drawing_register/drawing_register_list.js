// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Drawing Register"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return { "For construction": [__("For construction"), "green", "status,=,For construction"],
		         "For information": [__("For information"), "blue", "status,=,For information"],
		         Superseded: [__("Superseded"), "gray", "status,=,Superseded"] }[doc.status];
	},
};
