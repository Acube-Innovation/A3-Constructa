// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Snag Status"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
			get_query: () => {
				const project = frappe.query_report.get_filter_value("project");
				return project ? { filters: { project } } : {};
			},
		},
		{ fieldname: "trade", label: __("Trade"), fieldtype: "Select",
		  options: ["", "Civil", "Concrete", "Masonry", "Carpentry", "Tiling", "Painting", "Plastering", "Electrical", "Plumbing", "Glazing", "Roofing", "Metalwork", "Cleaning", "Other"] },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "open" && data.open > 0) return `<span class="text-danger">${value}</span>`;
		if (column.fieldname === "fixed" && data.fixed > 0) return `<span class="text-warning">${value}</span>`;
		if (column.fieldname === "overdue" && data.overdue > 0) return `<span class="text-danger">${value}</span>`;
		return value;
	},
};
