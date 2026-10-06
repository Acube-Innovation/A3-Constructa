// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Equipment Utilisation"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_months(frappe.datetime.get_today(), -1), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "asset", label: __("Machine"), fieldtype: "Link", options: "Asset" },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link", options: "Asset Category" },
		{ fieldname: "site", label: __("Site"), fieldtype: "Link", options: "Location" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "breakdown" && data.breakdown > 0) return `<span class="text-danger">${value}</span>`;
		return value;
	},
};
