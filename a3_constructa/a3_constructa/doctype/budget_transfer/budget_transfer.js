// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Budget Transfer", {
	setup(frm) {
		const wbs_query = () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} });
		frm.set_query("from_wbs", "items", wbs_query);
		frm.set_query("to_wbs", "items", wbs_query);
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Budget Revision Log"), () =>
				frappe.set_route("List", "Budget Revision Log", {
					reference_doctype: "Budget Transfer",
					reference_name: frm.doc.name,
				})
			);
		}
	},
});

frappe.ui.form.on("Budget Transfer Item", {
	from_wbs: show_available,
	from_cost_code: show_available,
	amount: (frm) => frm.set_value("total_amount", (frm.doc.items || []).reduce((t, r) => t + flt(r.amount), 0)),
});

// Shows what the From WBS can still give away, so the user sees the limit
// before the save checks it.
function show_available(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.from_wbs || !frm.doc.project) return;
	frappe
		.xcall("a3_constructa.a3_constructa.doctype.budget_transfer.budget_transfer.get_available_budget", {
			project: frm.doc.project,
			wbs: row.from_wbs,
			cost_code: row.from_cost_code,
		})
		.then((r) => {
			frappe.model.set_value(cdt, cdn, "available_budget", r.available);
			frappe.show_alert({
				message: __("{0}: budget {1}, committed {2}, spent {3}, available {4}", [
					row.from_wbs,
					format_currency(r.budget),
					format_currency(r.committed),
					format_currency(r.actual),
					format_currency(r.available),
				]),
				indicator: r.available > 0 ? "green" : "orange",
			}, 8);
		});
}
