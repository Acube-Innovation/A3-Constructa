// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Advance Recovery"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "awarded_quotation", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.expired && column.fieldname === "guarantee_expiry") {
			return `<span class="text-danger" title="${__("Expired with advance still to recover")}">${value}</span>`;
		}
		return value;
	},
};
