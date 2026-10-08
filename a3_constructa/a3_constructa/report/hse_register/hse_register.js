// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["HSE Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "view", label: __("View"), fieldtype: "Select", options: ["Weekly", "Open Permits", "Incidents"], default: "Weekly" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -83) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "state" && data.expired) return `<span class="text-danger"><b>${value}</b></span>`;
		if (column.fieldname === "incidents" && data.incidents) return `<span class="text-danger">${value}</span>`;
		if (column.fieldname === "talks" && data.talks === 0) return `<span class="text-warning">${value}</span>`;
		if (column.fieldname === "lost_time" && data.lost_time) return `<span class="text-danger"><b>${value}</b></span>`;
		if (column.fieldname === "status" && data.status !== "Closed") return `<span class="text-warning">${value}</span>`;
		return value;
	},
};
