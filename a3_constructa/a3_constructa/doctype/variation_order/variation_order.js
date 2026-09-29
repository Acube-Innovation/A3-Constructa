// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Variation Order", {
	setup(frm) {
		frm.set_query("awarded_quotation", () => ({ filters: { status: ["!=", "Cancelled"] } }));
		const same_project = () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} });
		frm.set_query("cost_head", "items", same_project);
		frm.set_query("wbs", "items", same_project);
	},
});

frappe.ui.form.on("Variation Order Item", {
	qty: update_amount,
	rate: update_amount,
	items_remove: update_total,
});

// The server recomputes both on save; this only keeps the form current while typing.
function update_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	update_total(frm);
}

function update_total(frm) {
	frm.set_value("total_amount", (frm.doc.items || []).reduce((sum, row) => sum + flt(row.amount), 0));
}
