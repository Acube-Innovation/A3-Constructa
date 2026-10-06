// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Approvals Pending"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "document_type", label: __("Document Type"), fieldtype: "Select",
		  options: ["", "Material Request", "Purchase Order"] },
		{ fieldname: "mine", label: __("Only Ones I Approve"), fieldtype: "Check" },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "status") {
			const colour = data.is_rejected ? "red" : data.is_mine ? "blue" : "orange";
			return `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		if (column.fieldname === "age_days" && data.age_days > 3) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
