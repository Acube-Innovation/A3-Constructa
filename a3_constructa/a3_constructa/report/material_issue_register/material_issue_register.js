// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Material Issue Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -1) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "cost_head", label: __("Cost Head"), fieldtype: "Link", options: "Cost Head" },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS" },
		{ fieldname: "cost_code", label: __("Cost Code"), fieldtype: "Link", options: "Cost Code" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
	],
};
