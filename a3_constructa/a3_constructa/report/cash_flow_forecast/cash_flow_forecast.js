// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
frappe.query_reports["Cash Flow Forecast"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
		  default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date",
		  default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date",
		  default: frappe.datetime.add_months(frappe.datetime.get_today(), 3), reqd: 1 },
		{ fieldname: "interval", label: __("Interval"), fieldtype: "Select",
		  options: ["Weekly", "Daily", "Monthly"], default: "Weekly" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// A forecast dipping below zero is the whole reason to run this.
		if (data && column.fieldname === "closing_balance" && data.closing_balance < 0) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		return value;
	},
};
