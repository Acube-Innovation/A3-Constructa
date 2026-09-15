// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Landed Cost Analysis"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "purchase_receipt", label: __("Purchase Receipt"), fieldtype: "Link",
		  options: "Purchase Receipt" },
		{ fieldname: "cost_code", label: __("Cost Code"), fieldtype: "Link",
		  options: "Cost Code" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		// Row 25 asks for per item and per cost code.
		{ fieldname: "group_by_cost_code", label: __("Group by Cost Code"),
		  fieldtype: "Check" },
	],
};
