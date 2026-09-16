// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Spare Consumption by Asset"] = {
	filters: [
		{ fieldname: "view", label: __("View"), fieldtype: "Select",
		  options: ["By Part", "By Asset"], default: "By Part" },
		{ fieldname: "asset", label: __("Asset"), fieldtype: "Link", options: "Asset" },
		{ fieldname: "asset_category", label: __("Asset Category"), fieldtype: "Link",
		  options: "Asset Category" },
		{ fieldname: "item_code", label: __("Part"), fieldtype: "Link", options: "Item" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
