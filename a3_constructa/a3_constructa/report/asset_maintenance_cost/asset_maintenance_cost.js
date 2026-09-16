// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Asset Maintenance Cost"] = {
	filters: [
		{ fieldname: "asset", label: __("Asset"), fieldtype: "Link", options: "Asset" },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link",
		  options: "Asset Category" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
