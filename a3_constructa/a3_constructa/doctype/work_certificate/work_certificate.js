// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 9.6: deductions, the compliance gate, and the subcontractor's invoice.
frappe.ui.form.on("Work Certificate", {
	setup(frm) {
		frm.set_query("subcontract_po", () => ({ filters: { docstatus: 1, ...(frm.doc.supplier ? { supplier: frm.doc.supplier } : {}) } }));
		const by_project = () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} });
		frm.set_query("wbs", by_project);
		frm.set_query("wbs", "deductions", by_project);
	},

	refresh(frm) {
		frm.set_intro();
		const issues = frm.doc.__onload?.compliance_issues || [];
		if (frm.doc.docstatus === 0 && issues.length) {
			frm.set_intro(__("Cannot be submitted yet. Compliance documents: {0}", [issues.join("; ")]), "red");
		}
		if (frm.doc.docstatus === 1 && !frm.doc.purchase_invoice) {
			frm.add_custom_button(__("Purchase Invoice"), () =>
				frappe.xcall("a3_constructa.a3_constructa.doctype.work_certificate.work_certificate.make_purchase_invoice", { work_certificate: frm.doc.name })
					.then((name) => frappe.set_route("Form", "Purchase Invoice", name))
			, __("Create"));
		}
	},
});
