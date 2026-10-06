// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Billing Schedule"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "awarded_quotation", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Planned", "Due", "Billed", "Paid", "Progress claims"] },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status") {
			const colour = { Due: "orange", Billed: "blue", Paid: "green", Planned: "gray", "Progress claims": "gray" }[data.status_key] || "gray";
			return `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
