// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Working Capital"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "to_date", label: __("As On"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "months", label: __("Months"), fieldtype: "Int", default: 12 },
	],
};
