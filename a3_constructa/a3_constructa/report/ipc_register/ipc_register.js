// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["IPC Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "awarded_quotation", label: __("Award"), fieldtype: "Link", options: "Awarded Quotation" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Submitted to Client", "Certified", "Invoiced"] },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && column.fieldname === "status") {
			const colour = { Draft: "gray", "Submitted to Client": "orange", Certified: "blue", Invoiced: "green" }[data.status] || "gray";
			return `<span class="indicator-pill ${colour}">${__(data.status)}${data.opening_invoice ? " · " + __("opening") : ""}</span>`;
		}
		return value;
	},
};
