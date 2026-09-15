// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Shipment TAT"] = {
	filters: [
		// Row 23 asks for averages by supplier, route and shipping line.
		{ fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
		  options: ["Milestone", "Supplier", "Service Route", "Shipping Line"],
		  default: "Milestone", reqd: 1 },
		{ fieldname: "view", label: __("View"), fieldtype: "Select",
		  options: ["Summary", "Detail"], default: "Summary" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "shipping_line", label: __("Shipping Line"), fieldtype: "Link",
		  options: "Supplier" },
		{ fieldname: "service_route", label: __("Service Route"), fieldtype: "Link",
		  options: "Service Route" },
	],
};
