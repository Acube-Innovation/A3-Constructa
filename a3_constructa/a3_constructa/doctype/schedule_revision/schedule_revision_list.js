// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.listview_settings["Schedule Revision"] = {
	add_fields: ["revision_no", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 0) return [__("Draft"), "red", "docstatus,=,0"];
		if (doc.docstatus === 2) return [__("Cancelled"), "gray", "docstatus,=,2"];
		return [__("Baseline {0}", [doc.revision_no]), "green", "docstatus,=,1"];
	},
};
