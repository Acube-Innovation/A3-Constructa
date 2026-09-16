// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Equipment Utilisation"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link",
		  options: "Asset Category" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
	],
};
