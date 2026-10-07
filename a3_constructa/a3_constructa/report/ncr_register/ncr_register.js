// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["NCR Register"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
			get_query: () => {
				const project = frappe.query_report.get_filter_value("project");
				return project ? { filters: { project } } : {};
			},
		},
		{ fieldname: "action_owner", label: __("Action Owner"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "include_closed", label: __("Include closed"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status") {
			const colour = { Open: "red", "Action Taken": "orange", Closed: "green" }[data.status] || "gray";
			return `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (column.fieldname === "overdue" && data.overdue > 0) return `<span class="text-danger">${value}</span>`;
		return value;
	},
};
