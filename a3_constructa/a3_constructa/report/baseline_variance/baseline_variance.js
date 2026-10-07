// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Baseline Variance"] = {
	filters: [
		// Not reqd: an empty required filter makes the page throw on load; the report asks for one instead.
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
		  get_query: () => ({ filters: { project: frappe.query_report.get_filter_value("project") } }) },
		{ fieldname: "revision", label: __("Against revision"), fieldtype: "Link", options: "Schedule Revision",
		  description: __("Empty: each task's current baseline"),
		  get_query: () => ({ filters: { project: frappe.query_report.get_filter_value("project"), docstatus: 1 } }) },
		{ fieldname: "view", label: __("Show"), fieldtype: "Select", options: ["Tasks", "WBS"], default: "Tasks" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["start_variance", "finish_variance", "finish_change", "worst"].includes(column.fieldname)) {
			const v = data[column.fieldname];
			if (v > 0) return `<div class="text-danger" style="text-align: right">+${v}</div>`;
			if (v < 0) return `<div class="text-success" style="text-align: right">${v}</div>`;
		}
		return value;
	},
};
