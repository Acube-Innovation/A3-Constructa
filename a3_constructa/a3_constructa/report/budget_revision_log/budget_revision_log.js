// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

const BRL_CHANGE_TYPES = {
	original: "Original",
	boq_revision: "BOQ Revision",
	variation: "Variation",
	transfer_in: "Transfer In",
	transfer_out: "Transfer Out",
};

frappe.query_reports["Budget Revision Log"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project",
		  get_query: () => {
			  const company = frappe.query_report.get_filter_value("company");
			  return { filters: company ? { company } : {} };
		  } },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
		  get_query: () => {
			  const project = frappe.query_report.get_filter_value("project");
			  return { filters: project ? { project } : {} };
		  } },
		{ fieldname: "cost_code", label: __("Cost Code"), fieldtype: "Link", options: "Cost Code" },
	],

	// Each amount opens the log rows behind it.
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const field = column.fieldname;
		if (!data || !data.wbs || !(field in BRL_CHANGE_TYPES || field === "revised" || field === "entries")) return value;
		if (field in BRL_CHANGE_TYPES && !data[field]) return value;
		const filters = { project: data.project, wbs: data.wbs };
		if (data.cost_code) filters.cost_code = data.cost_code;
		if (field in BRL_CHANGE_TYPES) filters.change_type = BRL_CHANGE_TYPES[field];
		const query = new URLSearchParams(filters).toString();
		return `<a href="/app/budget-revision-log?${query}" title="${__("Open the log rows")}">${value}</a>`;
	},
};
