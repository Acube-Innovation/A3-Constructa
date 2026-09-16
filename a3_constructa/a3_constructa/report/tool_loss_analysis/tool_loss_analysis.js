// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Tool Loss Analysis"] = {
	filters: [
		// Row 42 asks for loss by project, site, employee and item.
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Project", "Site", "Employee", "Item"], default: "Project", reqd: 1 },
		{ fieldname: "view", label: __("View"), fieldtype: "Select",
		  options: ["Summary", "Detail"], default: "Summary" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "site", label: __("Site"), fieldtype: "Link", options: "Location" },
		{ fieldname: "issued_to", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};
