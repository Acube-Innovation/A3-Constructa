// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Critical Path"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", reqd: 1 },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
		  get_query: () => ({ filters: { project: frappe.query_report.get_filter_value("project") } }) },
		{ fieldname: "show_all", label: __("All tasks, not only critical"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "total_float_days" && data.total_float_days <= 0) return `<b class="text-danger">${value}</b>`;
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__("Recalculate"), () =>
			frappe.xcall("a3_constructa.overrides.task.recalculate", { project: report.get_filter_value("project") }).then(() => report.refresh()));
	},
};
