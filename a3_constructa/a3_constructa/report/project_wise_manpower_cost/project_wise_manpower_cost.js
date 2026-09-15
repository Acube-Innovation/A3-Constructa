// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Project-wise Manpower Cost"] = {
	filters: [
		// Row 41 asks for project, cost head, WBS and cost code.
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Project", "Cost Head", "WBS", "Cost Code"], default: "Project", reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
	],
};
