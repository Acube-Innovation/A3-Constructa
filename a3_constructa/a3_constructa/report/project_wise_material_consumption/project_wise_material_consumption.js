// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Project-wise Material Consumption"] = {
	filters: [
		// Row 22 asks for grouping by project, cost head, WBS and cost code.
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Project", "Cost Head", "WBS", "Cost Code"], default: "Project",
		  reqd: 1 },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
