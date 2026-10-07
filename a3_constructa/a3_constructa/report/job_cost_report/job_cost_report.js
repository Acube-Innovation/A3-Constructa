// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 13.1: every figure opens the documents behind it, with the same filters.
const DRILL = {
	original_budget: { doctype: "WBS Allocation", map: (d) => ({ project: d.project, wbs: d.wbs, "WBS Allocation Item.cost_code": d.cost_code, docstatus: ["<", 2] }) },
	budget_changes: { doctype: "Budget Revision Log", map: (d) => ({ project: d.project, wbs: d.wbs, cost_code: d.cost_code,
		change_type: ["in", ["Variation", "Transfer In", "Transfer Out"]] }) },
	committed: { doctype: "Purchase Order", map: (d) => ({ project: d.project, docstatus: 1, per_billed: ["<", 100], "Purchase Order Item.wbs": d.wbs, "Purchase Order Item.cost_code": d.cost_code }) },
};

frappe.query_reports["Job Cost Report"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "as_on", label: __("As on"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "depth", label: __("Depth"), fieldtype: "Select", options: ["Cost Code", "WBS", "Work Package", "Cost Head", "Project"], default: "Cost Code" },
		{ fieldname: "hide_zero", label: __("Hide zero rows"), fieldtype: "Check", default: 1 },
	],
	tree: true,
	name_field: "key",
	parent_field: "parent_key",
	initial_depth: 3,
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "label") {
			const strong = data.level === "Project" || data.level === "Cost Head";
			return data.is_unallocated ? `<span class="text-muted"><i>${value}</i></span>` : strong ? `<b>${value}</b>` : value;
		}
		if (["variance"].includes(column.fieldname) && data.variance < -0.005) value = `<span class="text-danger">${value}</span>`;
		if (["original_budget", "budget_changes", "committed", "actual"].includes(column.fieldname) && Math.abs(data[column.fieldname]) >= 0.005) {
			return `<a class="jc-drill" data-figure="${column.fieldname}" data-key="${encodeURIComponent(data.key)}">${value}</a>`;
		}
		return value;
	},
	onload(report) {
		$(report.page.wrapper).on("click", "a.jc-drill", (e) => {
			e.preventDefault();
			const key = decodeURIComponent(e.currentTarget.dataset.key);
			const row = (report.data || []).find((r) => r.key === key);
			if (!row) return;
			const figure = e.currentTarget.dataset.figure;
			const clean = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== null));
			if (figure === "actual") return actual_dialog(row.drill, report.get_filter_value("as_on"));
			const { doctype, map } = DRILL[figure];
			frappe.route_options = clean(map(row.drill));
			frappe.set_route("List", doctype);
		});
	},
};

// Actual cost has two sources: expense entries in the ledger, and material issued from store.
function actual_dialog(d, as_on) {
	const open = (doctype, options) => {
		dialog.hide();
		frappe.route_options = Object.fromEntries(Object.entries(options).filter(([, v]) => v !== undefined && v !== null));
		frappe.set_route("List", doctype);
	};
	const dialog = new frappe.ui.Dialog({
		title: __("Actual cost: open the documents"),
		fields: [{ fieldtype: "HTML", fieldname: "links" }],
	});
	const wrap = dialog.fields_dict.links.$wrapper;
	wrap.html(`<p class="text-muted">${__("Actual cost is the ledger's expense entries plus material issued to the job, up to {0}.", [frappe.datetime.str_to_user(as_on)])}</p>`);
	$(`<button class="btn btn-default btn-sm" style="margin-right:8px">${__("Ledger entries")}</button>`).appendTo(wrap).on("click", () =>
		open("GL Entry", { project: d.project, wbs: d.wbs, cost_code: d.cost_code, is_cancelled: 0, posting_date: ["<=", as_on] }));
	$(`<button class="btn btn-default btn-sm">${__("Material issued")}</button>`).appendTo(wrap).on("click", () =>
		open("Stock Entry", { docstatus: 1, purpose: "Material Issue", "Stock Entry Detail.project": d.project, "Stock Entry Detail.wbs": d.wbs,
			"Stock Entry Detail.cost_code": d.cost_code, posting_date: ["<=", as_on] }));
	dialog.show();
}
