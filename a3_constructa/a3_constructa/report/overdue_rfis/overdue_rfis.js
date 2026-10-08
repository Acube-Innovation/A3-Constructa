// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Overdue RFIs"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "addressed_to", label: __("Waiting On"), fieldtype: "Data" },
		{ fieldname: "due_within", label: __("Also Due Within (days)"), fieldtype: "Int", default: 0 },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "days_overdue" && data.days_overdue > 0) return `<span class="text-danger"><b>${value}</b></span>`;
		if (column.fieldname === "required_by" && !data.overdue) return `<span class="text-warning">${value}</span>`;
		return value;
	},
};
