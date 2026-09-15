// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Cost to Complete"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "cost_code", label: __("Cost Code"), fieldtype: "Link", options: "Cost Code" },
		{ fieldname: "only_adverse", label: __("Only Adverse Forecast"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "forecast_variance" && data.forecast_variance < 0) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
