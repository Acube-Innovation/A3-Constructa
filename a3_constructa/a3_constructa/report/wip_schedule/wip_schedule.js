// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 13.4: over-billing (billed ahead of the work) in orange; a forecast loss in red.
frappe.query_reports["WIP Schedule"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "awarded_quotation", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "as_on", label: __("As on"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "over_under" && Math.abs(data.over_under) >= 0.005) {
			const over = data.over_under > 0;
			return `<span style="color: var(--${over ? "orange" : "blue"}-600); font-weight:600">${value}</span> <span class="text-muted small">${over ? __("over") : __("under")}</span>`;
		}
		if (["forecast_profit", "recognised"].includes(column.fieldname) && data[column.fieldname] < -0.005) {
			return `<span class="text-danger" style="font-weight:600">${value}</span>`;
		}
		return value;
	},
};
