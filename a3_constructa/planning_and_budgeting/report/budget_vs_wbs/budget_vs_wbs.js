// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Budget vs WBS"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
