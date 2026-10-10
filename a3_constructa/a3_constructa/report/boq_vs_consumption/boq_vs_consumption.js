// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.query_reports["BOQ vs Consumption"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "cost_code", label: __("Cost Code"), fieldtype: "Link", options: "Cost Code" },
		{ fieldname: "to_date", label: __("As On"), fieldtype: "Date" },
		{ fieldname: "only_over_consumed", label: __("Only Over-Use"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		// Over-use is the thing to notice, so it is coloured; an item never in the BOQ says so.
		if (data.over_consumed && ["issued_qty", "balance_qty", "consumed_percent", "over_qty", "over_value"].includes(column.fieldname)) {
			value = `<span style="color: var(--red-600); font-weight: 600">${value}</span>`;
		}
		if (column.fieldname === "item_code" && data.not_in_boq) value += ` <span class="text-danger small">${__("not in BOQ")}</span>`;
		if (column.fieldname === "issued_qty" && data.issued_qty) {
			value = `<a class="bvc-issued" data-project="${encodeURIComponent(data.project)}" data-item="${encodeURIComponent(data.item_code)}" data-cc="${encodeURIComponent(data.cost_code)}" data-wbs="${encodeURIComponent(data.wbs || "")}">${value}</a>`;
		}
		return value;
	},
	onload(report) {
		$(report.page.wrapper).on("click", "a.bvc-issued", (e) => {
			e.preventDefault();
			const d = e.currentTarget.dataset;
			frappe.route_options = { docstatus: 1, purpose: "Material Issue", "Stock Entry Detail.project": decodeURIComponent(d.project),
				"Stock Entry Detail.item_code": decodeURIComponent(d.item), "Stock Entry Detail.cost_code": decodeURIComponent(d.cc) };
			if (d.wbs) frappe.route_options["Stock Entry Detail.wbs"] = decodeURIComponent(d.wbs);
			frappe.set_route("List", "Stock Entry");
		});
	},
};
