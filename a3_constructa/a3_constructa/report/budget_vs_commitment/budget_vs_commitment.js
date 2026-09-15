// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Budget vs Commitment"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		// Row 17 asks for "grouped by cost_code / wbs" - both, switchable.
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Cost Code", "WBS"], default: "Cost Code", reqd: 1 },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
