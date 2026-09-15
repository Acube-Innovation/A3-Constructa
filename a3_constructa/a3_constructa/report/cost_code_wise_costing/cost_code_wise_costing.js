// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Cost Code Wise Costing"] = {
	filters: [
		// Row 32 groups by project, cost head, WBS and cost code; row 37 reuses
		// this report with the WBS grouping.
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Cost Code", "WBS", "Cost Head", "Project"], default: "Cost Code", reqd: 1 },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "only_over_budget", label: __("Only Over Budget"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "percent_consumed") {
			// The thresholds row 59's number card uses.
			const pct = data.percent_consumed;
			if (pct > 100) value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
			else if (pct > 85) value = `<span style="color: var(--orange-600); font-weight: 600">${value}</span>`;
		}
		if (data && column.fieldname === "balance" && data.balance < 0) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
