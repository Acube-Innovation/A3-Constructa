// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

const WBS_STATUS_COLOURS = { Draft: "gray", Active: "green", "On Hold": "orange", Completed: "blue" };

frappe.query_reports["WBS Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project",
		  get_query: () => {
			  const company = frappe.query_report.get_filter_value("company");
			  return { filters: company ? { company } : {} };
		  } },
		{ fieldname: "cost_head", label: __("Cost Head"), fieldtype: "Link", options: "Cost Head" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: ["", "Draft", "Active", "On Hold", "Completed"] },
	],
	tree: true,
	name_field: "wbs",
	parent_field: "parent_wbs",
	initial_depth: 4,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status) {
			const colour = WBS_STATUS_COLOURS[data.status] || "gray";
			return `<span class="indicator-pill ${colour}">${frappe.utils.escape_html(__(data.status))}</span>`;
		}
		return value;
	},
};
