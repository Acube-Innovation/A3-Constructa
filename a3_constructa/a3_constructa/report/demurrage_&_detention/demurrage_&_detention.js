// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Demurrage & Detention"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "shipping_line", label: __("Shipping Line"), fieldtype: "Link",
		  options: "Supplier" },
		{ fieldname: "service_route", label: __("Service Route"), fieldtype: "Link",
		  options: "Service Route" },
		{ fieldname: "only_with_cost", label: __("Only Shipments with Demurrage"),
		  fieldtype: "Check", default: 1 },
	],
};
