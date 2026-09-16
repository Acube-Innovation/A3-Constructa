// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Tools Outstanding"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "site", label: __("Site"), fieldtype: "Link", options: "Location" },
		{ fieldname: "issued_to", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "item_code", label: __("Tool"), fieldtype: "Link", options: "Item" },
		{ fieldname: "only_overdue", label: __("Only Overdue"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.overdue && ["days_outstanding", "expected_return_date"].includes(column.fieldname)) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
