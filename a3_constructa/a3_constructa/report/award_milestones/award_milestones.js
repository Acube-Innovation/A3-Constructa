// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Award Milestones"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "award", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: ["", "Not Started", "In Progress", "Overdue", "Completed"] },
		{ fieldname: "overdue_only", label: __("Overdue Only"), fieldtype: "Check" },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status") {
			const colour = { Overdue: "red", Completed: "green", "In Progress": "blue" }[data.status] || "gray";
			return `<span class="indicator-pill ${colour}">${__(data.status)}</span>`;
		}
		if (column.fieldname === "variance_days" && data.variance_days > 0) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
