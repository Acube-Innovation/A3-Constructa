// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Snag List", {
	setup(frm) {
		frm.set_query("wbs", () => ({ filters: { project: frm.doc.project } }));
		frm.set_query("responsible", "items", (doc, cdt, cdn) =>
			locals[cdt][cdn].responsible_type === "Crew" ? { filters: { is_active: 1 } } : {});
	},
});
