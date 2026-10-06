// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Unallocated BOQ Lines"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project",
		  get_query: () => {
			  const company = frappe.query_report.get_filter_value("company");
			  return { filters: company ? { company } : {} };
		  } },
		{ fieldname: "cost_head", label: __("Cost Head"), fieldtype: "Link", options: "Cost Head" },
		{ fieldname: "boq", label: __("BOQ"), fieldtype: "Link", options: "BOQ",
		  get_query: () => ({ filters: { docstatus: 1 } }) },
	],
};
