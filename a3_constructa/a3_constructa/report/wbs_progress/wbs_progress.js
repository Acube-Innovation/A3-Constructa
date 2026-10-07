// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["WBS Progress"] = {
	filters: [
		// Not reqd: an empty required filter makes the page throw on load; the report asks for one instead.
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "as_of", label: __("As of"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],
	tree: true,
	name_field: "wbs",
	parent_field: "parent_wbs",
	initial_depth: 2,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["variance", "schedule_variance"].includes(column.fieldname) && data[column.fieldname] < 0) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
