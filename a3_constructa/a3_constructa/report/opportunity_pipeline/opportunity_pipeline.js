// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Opportunity Pipeline"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Sales Stage", "Award Month"], default: "Sales Stage" },
		{ fieldname: "sector", label: __("Sector"), fieldtype: "Select",
		  options: ["", "Government", "Infrastructure", "Healthcare", "Education", "Commercial", "Residential", "Industrial"] },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "User" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: ["", "Open", "Replied", "Quotation", "Converted", "Lost", "Closed"],
		  description: __("Blank shows the live pipeline: Open, Replied and Quotation.") },
		{ fieldname: "due_soon", label: __("Due Soon (7 days, not quoted)"), fieldtype: "Check" },
	],
	tree: true,
	name_field: "id",
	parent_field: "parent_id",
	initial_depth: 2,

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (data.is_group && ["label", "value", "weighted"].includes(column.fieldname)) {
			return `<b>${value}</b>`;
		}
		if (column.fieldname === "tender_due_date" && data.due_soon) {
			return `<span class="text-danger" title="${__("Due within 7 days and not quoted yet")}"><b>${value}</b></span>`;
		}
		return value;
	},
};
