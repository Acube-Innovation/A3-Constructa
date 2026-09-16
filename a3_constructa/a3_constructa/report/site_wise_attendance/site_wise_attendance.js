// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Site-wise Attendance"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_days(frappe.datetime.get_today(), -7), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "site", label: __("Site"), fieldtype: "Link", options: "Location" },
		{ fieldname: "shift", label: __("Shift"), fieldtype: "Link", options: "Shift Type" },
	],
};
