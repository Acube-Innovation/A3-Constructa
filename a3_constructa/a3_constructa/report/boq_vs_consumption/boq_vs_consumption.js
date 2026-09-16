// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["BOQ vs Consumption"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "cost_code", label: __("Cost Code"), fieldtype: "Link", options: "Cost Code" },
		{ fieldname: "to_date", label: __("As On"), fieldtype: "Date" },
		{ fieldname: "only_over_consumed", label: __("Only Over-Consumed"),
		  fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Over-consumption is the thing to notice, so it is coloured.
		if (data && data.over_consumed && ["issued_qty", "balance_qty", "consumed_percent"]
				.includes(column.fieldname)) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
