// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 7.6: fewer on site than planned in orange; more than planned in blue.
frappe.query_reports["Manpower Histogram"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "trade", label: __("Trade"), fieldtype: "Select",
		  options: ["", "Tiling", "Masonry", "Concrete", "Steel fixing", "Formwork", "Carpentry", "Electrical", "Plumbing", "Painting", "Plant operators", "General labour"] },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -42) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 28) },
	],
	tree: true,
	name_field: "key",
	parent_field: "parent_key",
	initial_depth: 1,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "label" && !data.parent_key) return `<b>${value}</b>`;
		if (column.fieldname === "difference" && data.week <= frappe.datetime.get_today() && Math.abs(data.difference) > 0) {
			return `<span style="color: var(--${data.difference < 0 ? "orange" : "blue"}-600); font-weight:600">${value}</span>`;
		}
		return value;
	},
};
