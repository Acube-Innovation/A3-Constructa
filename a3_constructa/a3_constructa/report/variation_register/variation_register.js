// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Variation Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "awarded_quotation", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: ["", "Draft", "Submitted to Client", "Approved", "Rejected", "Cancelled"] },
		{ fieldname: "variation_type", label: __("Type"), fieldtype: "Select", options: ["", "Addition", "Omission", "Substitution"] },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status") {
			const colour = { Approved: "green", "Submitted to Client": "orange", Draft: "blue", Rejected: "red", Cancelled: "gray" }[data.status] || "gray";
			return `<span class="indicator-pill ${colour}">${__(data.status)}</span>`;
		}
		if (column.fieldname === "total_amount" && data.total_amount < 0) return `<span class="text-danger">${value}</span>`;
		return value;
	},
};
