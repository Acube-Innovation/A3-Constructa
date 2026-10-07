// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Certificates Expiring"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "days", label: __("Days ahead"), fieldtype: "Int", default: 60 },
		{ fieldname: "certificate_type", label: __("Certificate"), fieldtype: "Select",
		  options: ["", "Trade test", "Operator licence", "Work at height", "Welding", "Scaffolding", "Confined space", "First aid", "Driving licence"] },
		{ fieldname: "include_expired", label: __("Include expired"), fieldtype: "Check", default: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data || column.fieldname !== "status") return value;
		const colour = data.days_left < 0 || data.days_left <= 7 ? "red" : data.days_left <= 30 ? "orange" : "blue";
		return `<span class="indicator-pill ${colour}">${value}</span>`;
	},
};
