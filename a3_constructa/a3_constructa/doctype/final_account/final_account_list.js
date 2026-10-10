// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Final Account"] = {
	add_fields: ["status", "balance_due"],
	get_indicator(doc) {
		const colour = { Draft: "red", Agreed: "orange", Closed: "green" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
