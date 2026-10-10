// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Change Event Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "awarded_quotation", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: ["", "Open", "Priced", "Claim", "Became VO", "Absorbed", "Closed"] },
		{ fieldname: "open_only", label: __("Open Exposure Only"), fieldtype: "Check",
		  description: __("Open, Priced and Claim: not yet decided, or contested") },
	],
	tree: true,
	name_field: "id",
	parent_field: "parent_id",
	initial_depth: 2,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (data.indent === 0 && column.fieldname === "rough_cost") {
			return `<b title="${__("Open exposure: Open, Priced and Claim")}">${value}</b>`;
		}
		if (data.is_group && column.fieldname === "label") {
			const colour = data.indent === 1 ? (data.is_open ? "text-warning" : "text-muted") : "";
			return `<b class="${colour}">${value}</b>`;
		}
		return value;
	},
};
