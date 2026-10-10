// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 13.3: below 1.0, an index is behind the plan (SPI) or over cost (CPI).
frappe.query_reports["Earned Value"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		// A WBS names its own project, so the report reads the project from it.
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
		  get_query: () => ({ filters: frappe.query_report.get_filter_value("project") ? { project: frappe.query_report.get_filter_value("project") } : {} }) },
		{ fieldname: "as_on", label: __("As on"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "period", label: __("S-curve by"), fieldtype: "Select", options: ["Weekly", "Monthly"], default: "Weekly" },
	],
	tree: true,
	name_field: "key",
	parent_field: "parent_key",
	initial_depth: 2,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "label") {
			if (data.level === "Project") return `<b>${value}</b>`;
			if (data.level === "No WBS") return `<span class="text-muted"><i>${value}</i></span>`;
			return value;
		}
		const v = data[column.fieldname];
		if (["spi", "cpi"].includes(column.fieldname) && v !== null && v !== undefined && v < 1) {
			return `<span class="text-danger" style="font-weight:600">${value}</span>`;
		}
		if (["sv", "cv", "vac"].includes(column.fieldname) && v < -0.005) return `<span class="text-danger">${value}</span>`;
		return value;
	},
};
