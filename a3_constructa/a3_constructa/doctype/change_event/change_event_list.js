// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Change Event"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = { Open: "orange", Priced: "blue", "Became VO": "green", Absorbed: "gray", Claim: "red", Closed: "gray" }[doc.status];
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
