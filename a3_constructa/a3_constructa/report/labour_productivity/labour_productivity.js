// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 7.5: a productivity factor below 0.85 (planned ÷ actual hours) is flagged.
const LP_TRADES = ["", "Tiling", "Masonry", "Concrete", "Steel fixing", "Formwork", "Carpentry", "Electrical", "Plumbing", "Painting", "Plant operators", "General labour"];
frappe.query_reports["Labour Productivity"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "trade", label: __("Trade"), fieldtype: "Select", options: LP_TRADES },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -56) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "only_with_hours", label: __("Only weeks with crew hours"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "factor" && data.flag) return `<span class="text-danger" style="font-weight:600">${value}</span>`;
		if (column.fieldname === "factor" && data.factor) return `<span class="text-success">${value}</span>`;
		if (column.fieldname === "trade" && !data.hours) return `<span class="text-muted">${value}</span>`;
		return value;
	},
};
