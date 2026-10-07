// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Equipment Plan"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "category", label: __("Category"), fieldtype: "Link", options: "Asset Category" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "weeks", label: __("Weeks"), fieldtype: "Int", default: 12 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (["shortfall", "double_bookings"].includes(column.fieldname) && data[column.fieldname]) return `<span class="text-danger">${value}</span>`;
		if (column.fieldname === "movement" && data.movement) return `<span class="text-warning">${value}</span>`;
		return value;
	},
};
