// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Bid Decisions"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "stage", label: __("Decision"), fieldtype: "Select",
		  options: ["", "Not scored", "Scoring", "Awaiting decision", "Go", "No-go"] },
		{ fieldname: "sector", label: __("Sector"), fieldtype: "Select",
		  options: ["", "Government", "Infrastructure", "Healthcare", "Education", "Commercial", "Residential", "Industrial"] },
		{ fieldname: "from_date", label: __("Tender Due From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Tender Due To"), fieldtype: "Date" },
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "stage") {
			const color = { Go: "green", "No-go": "red", "Awaiting decision": "orange", Scoring: "blue" }[data.stage_key] || "gray";
			return `<span class="indicator-pill ${color}">${value}</span>`;
		}
		if (column.fieldname === "total_score" && data.total_score !== null && data.total_score < data.threshold) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
