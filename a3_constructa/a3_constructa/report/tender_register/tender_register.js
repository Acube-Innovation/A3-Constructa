// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Tender Register"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "opportunity", label: __("Tender"), fieldtype: "Link", options: "Opportunity" },
		{ fieldname: "include_answered", label: __("Answered queries too"), fieldtype: "Check" },
		{ fieldname: "include_closed", label: __("Closed tenders too"), fieldtype: "Check" },
	],
	tree: true,
	initial_depth: 1,
	name_field: "label",
	parent_field: "",

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "label" && data.indent === 0) return `<b>${value}</b>`;
		if (column.fieldname === "label" && data.doctype === "Tender Clarification") {
			return `<a href="/app/tender-clarification/${encodeURIComponent(data.reference)}">${value}</a>`;
		}
		if (column.fieldname === "reference" && data.doctype === "Opportunity") {
			return `<a href="/app/opportunity/${encodeURIComponent(data.reference)}">${value}</a>`;
		}
		if (column.fieldname === "reference" && data.reference && data.reference.startsWith("/")) {
			return `<a href="${encodeURI(data.reference)}" target="_blank">${__("Open file")}</a>`;
		}
		if (column.fieldname === "status") {
			if (data.doctype === "Tender Clarification" && data.status !== "Answered") return `<span class="text-warning">${value}</span>`;
			if (data.status === "Superseded") return `<span class="text-muted"><s>${value}</s></span>`;
		}
		if (column.fieldname === "days" && data.doctype === "Tender Clarification" && data.status === "Open" && data.days > 7) {
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
