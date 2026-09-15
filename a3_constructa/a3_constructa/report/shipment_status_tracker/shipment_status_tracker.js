// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Shipment Status Tracker"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "shipment_type", label: __("Shipment Type"), fieldtype: "Select",
		  options: ["", "Domestic", "Import"] },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select",
		  options: ["", "Draft", "Supplier Despatched", "In Transit", "Arrived at Port",
			    "Under Customs Clearance", "Cleared", "In Inland Transit",
			    "Received at Warehouse", "Received at Site", "Closed"] },
	],
};
