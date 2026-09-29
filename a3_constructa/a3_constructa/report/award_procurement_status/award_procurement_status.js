// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["Award Procurement Status"] = {
	filters: [
		{
			fieldname: "awarded_quotation",
			label: __("Awarded Quotation"),
			fieldtype: "Link",
			options: "Awarded Quotation",
		},
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "boq",
			label: __("BOQ"),
			fieldtype: "Link",
			options: "BOQ",
			get_query: () => {
				const filters = { docstatus: 1 };
				const award = frappe.query_report.get_filter_value("awarded_quotation");
				const project = frappe.query_report.get_filter_value("project");
				if (award) filters.awarded_quotation = award;
				if (project) filters.project = project;
				return { filters };
			},
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "stage",
			label: __("Show"),
			fieldtype: "Select",
			options: ["", "To request", "To order", "To receive", "Fully received", "Over requested"].join("\n"),
		},
	],
};
