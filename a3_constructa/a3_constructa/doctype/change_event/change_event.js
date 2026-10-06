// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Change Event", {
	setup(frm) {
		frm.set_query("awarded_quotation", () => ({ filters: { status: ["!=", "Cancelled"] } }));
		frm.set_query("wbs", () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.raised_by) {
			frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then(({ message }) => {
				if (message && message.name) frm.set_value("raised_by", message.name);
			});
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.status === "Priced" && !frm.doc.variation_order) {
			frm.add_custom_button(__("Variation Order"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save the change event first."));
					return;
				}
				frappe
					.xcall("a3_constructa.a3_constructa.doctype.change_event.change_event.make_variation_order", {
						change_event: frm.doc.name,
					})
					.then((name) => frappe.set_route("Form", "Variation Order", name));
			}, __("Create"));
		}
		if (frm.doc.status === "Open") {
			frm.set_intro(__("Give it a rough cost or rough days, then mark it Priced to decide what happens to it."), "blue");
		}
	},
});
