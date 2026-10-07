// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 13.2: each quantity opens the documents behind it, with the same filters.
const QC_DRILL = {
	boq_qty: (d) => ["BOQ", { project: d.project, docstatus: 1, "BOQ Item.item_code": d.item_code }],
	allocated_qty: (d) => ["WBS Allocation", { project: d.project, docstatus: 1, wbs: d.wbs, "WBS Allocation Item.item_code": d.item_code }],
	requested_qty: (d) => ["Material Request", { docstatus: 1, "Material Request Item.project": d.project, "Material Request Item.item_code": d.item_code, "Material Request Item.wbs": d.wbs }],
	ordered_qty: (d) => ["Purchase Order", { docstatus: 1, "Purchase Order Item.project": d.project, "Purchase Order Item.item_code": d.item_code, "Purchase Order Item.wbs": d.wbs }],
	received_qty: (d) => ["Purchase Receipt", { docstatus: 1, "Purchase Receipt Item.project": d.project, "Purchase Receipt Item.item_code": d.item_code, "Purchase Receipt Item.wbs": d.wbs }],
	issued_qty: (d) => ["Stock Entry", { docstatus: 1, purpose: "Material Issue", "Stock Entry Detail.project": d.project, "Stock Entry Detail.item_code": d.item_code, "Stock Entry Detail.wbs": d.wbs }],
};

frappe.query_reports["Quantity Chain"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: frappe.defaults.get_user_default("Company"), reqd: 1 },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "boq", label: __("BOQ"), fieldtype: "Link", options: "BOQ", get_query: () => ({ filters: { docstatus: 1 } }) },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "stage", label: __("Stage"), fieldtype: "Select", options: ["", "To request", "To order", "To receive", "Over-requested", "Over-issued"] },
		{ fieldname: "to_date", label: __("Issued up to"), fieldtype: "Date" },
		{ fieldname: "hide_complete", label: __("Hide complete lines"), fieldtype: "Check" },
	],
	tree: true,
	name_field: "key",
	parent_field: "parent_key",
	initial_depth: 2,
	formatter(value, row, column, data, default_formatter) {
		if (data && data.level === "Project" && column.fieldtype === "Float") return ""; // items in different units never add up
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "label") {
			if (data.level === "Project") return `<b>${value}</b>`;
			if (data.level === "WBS" && !data.wbs) return `<span class="text-muted"><i>${value}</i></span>`;
			if (data.level === "Item" && !data.in_boq) return `${value} <span class="text-danger small">${__("not in BOQ")}</span>`;
			return value;
		}
		if (column.fieldname === "stage" && data.stage) {
			const bad = /Over-/.test(data.stage) || (data.level === "WBS" && !data.in_boq);
			const color = bad ? "red" : data.stage === __("Complete") ? "green" : "orange";
			return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(data.stage)}</span>`;
		}
		if (column.fieldname === "issued_qty" && data.issued_qty - (data.allowed_qty || 0) > 1e-6) value = `<span class="text-danger">${value}</span>`;
		if (QC_DRILL[column.fieldname] && data.level !== "Project" && Math.abs(data[column.fieldname] || 0) > 1e-9) {
			return `<a class="qc-drill" data-figure="${column.fieldname}" data-key="${encodeURIComponent(data.key)}">${value}</a>`;
		}
		return value;
	},
	onload(report) {
		$(report.page.wrapper).on("click", "a.qc-drill", (e) => {
			e.preventDefault();
			const row = (report.data || []).find((r) => r.key === decodeURIComponent(e.currentTarget.dataset.key));
			if (!row) return;
			const [doctype, options] = QC_DRILL[e.currentTarget.dataset.figure](row.drill);
			// An item row covers every WBS: drop the empty WBS key rather than filter on "not set".
			frappe.route_options = Object.fromEntries(Object.entries(options).filter(([, v]) => v !== undefined && v !== null && v !== ""));
			frappe.set_route("List", doctype);
		});
	},
};
