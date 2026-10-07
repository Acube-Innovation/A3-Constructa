// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 6.4: freeze the programme as a baseline.
frappe.ui.form.on("Schedule Revision", {
	setup(frm) {
		frm.set_query("variation_order", () => ({ filters: { status: "Approved" } }));
	},
	refresh(frm) {
		frm.set_intro();
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.set_intro(__("Draft: the table shows what Submit will freeze as revision {0}. Save again to refresh it from the tasks.", [frm.doc.revision_no]), "blue");
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Baseline Variance"), () => frappe.set_route("query-report", "Baseline Variance", { project: frm.doc.project }));
		}
	},
});
