// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Quotation Revisions"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), -6) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "boq", label: __("BOQ"), fieldtype: "Link", options: "BOQ",
		  get_query: () => ({ filters: { boq_stage: "Tender" } }) },
		{ fieldname: "only_revised", label: __("Only Revised Quotations"), fieldtype: "Check" },
	],
	tree: true,
	name_field: "id",
	parent_field: "parent_id",
	initial_depth: 1,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (data.is_group && ["label", "value"].includes(column.fieldname)) return `<b>${value}</b>`;
		if (column.fieldname === "change" && data.change) {
			return `<span class="${data.change < 0 ? "text-danger" : "text-success"}">${value}</span>`;
		}
		if (column.fieldname === "approval" && data.approval === __("Pending Management Approval")) {
			return `<span class="text-warning"><b>${value}</b></span>`;
		}
		if (column.fieldname === "approval" && data.approval === __("Superseded")) {
			return `<span class="text-muted">${value}</span>`;
		}
		return value;
	},
};
