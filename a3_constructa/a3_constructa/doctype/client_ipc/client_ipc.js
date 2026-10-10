// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Client IPC", {
	setup(frm) {
		frm.set_query("awarded_quotation", () => ({ filters: { status: ["in", ["Awarded", "In Progress", "On Hold", "Completed"]] } }));
		frm.set_query("wbs", "items", () => ({ filters: frm.doc.project ? { project: frm.doc.project, status: "Active" } : {} }));
		frm.set_query("opening_invoice", () => ({ filters: { awarded_quotation: frm.doc.awarded_quotation, docstatus: 1 } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.awarded_quotation) {
			frm.add_custom_button(__("Get contract lines"), () => {
				frappe.xcall("a3_constructa.a3_constructa.doctype.client_ipc.client_ipc.get_contract_lines", { award: frm.doc.awarded_quotation })
					.then((lines) => {
						const have = new Set((frm.doc.items || []).map((r) => r.line_key));
						lines.filter((l) => !have.has(l.line_key)).forEach((l) => frm.add_child("items", l));
						frm.refresh_field("items");
						frappe.show_alert({ message: __("{0} contract lines", [lines.length]), indicator: "green" });
					});
			});
			if (frm.doc.status === "Draft" && !frm.is_new()) {
				frm.add_custom_button(__("Mark Submitted to Client"), () => {
					frm.set_value("status", "Submitted to Client");
					frm.save();
				});
			}
		}
		if (frm.doc.docstatus === 1 && frm.doc.status === "Certified" && !frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () =>
				frappe.xcall("a3_constructa.a3_constructa.doctype.client_ipc.client_ipc.make_sales_invoice", { ipc: frm.doc.name })
					.then((name) => frappe.set_route("Form", "Sales Invoice", name))
			, __("Create"));
		}
		if (frm.doc.status === "Submitted to Client" && frm.doc.docstatus === 0) {
			frm.set_intro(__("With the client: enter what the engineer certifies in Certified This Period, then Submit to certify."), "blue");
		}
	},
});
