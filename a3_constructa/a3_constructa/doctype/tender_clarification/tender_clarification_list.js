// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Tender Clarification"] = {
	get_indicator(doc) {
		if (doc.status === "Open") return [__("Open"), "orange", "status,=,Open"];
		return doc.price_impact ? [__("Answered, price impact"), "purple", "price_impact,=,1"] : [__("Answered"), "green", "status,=,Answered"];
	},
	add_fields: ["price_impact"],
};
