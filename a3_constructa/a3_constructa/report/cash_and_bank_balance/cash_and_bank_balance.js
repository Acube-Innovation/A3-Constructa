// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Cash and Bank Balance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "as_on", label: __("As On"), fieldtype: "Date",
		  default: frappe.datetime.get_today() },
	],
};
