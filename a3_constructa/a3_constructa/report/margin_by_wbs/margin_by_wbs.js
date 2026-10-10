// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 13.4: certified revenue against actual cost, by WBS. A loss is in red.
frappe.query_reports["Margin by WBS"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "as_on", label: __("As on"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "hide_zero", label: __("Hide rows with nothing"), fieldtype: "Check", default: 1 },
	],
	tree: true,
	name_field: "key",
	parent_field: "parent_key",
	initial_depth: 3,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "label") {
			if (data.level === "Project") return `<b>${value}</b>`;
			if (data.level === "No WBS") return `<span class="text-muted"><i>${value}</i></span>`;
			return value;
		}
		if (["margin", "margin_percent"].includes(column.fieldname) && data[column.fieldname] < -0.005) {
			return `<span class="text-danger" style="font-weight:600">${value}</span>`;
		}
		return value;
	},
};
