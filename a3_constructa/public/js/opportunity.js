// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Opportunity: Create > Tender BOQ (catalogue 2.4). Opens a new Tender BOQ with
// the opportunity, client and currency set, ready for the client's bill to be
// imported with "Import lines".
frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2 || ["Lost", "Closed"].includes(frm.doc.status)) return;
		frm.add_custom_button(
			__("Tender BOQ"),
			() =>
				frappe
					.xcall("a3_constructa.api.boq_import.make_tender_boq", { opportunity: frm.doc.name })
					.then((doc) => {
						const boq = frappe.model.sync(doc)[0];
						frappe.set_route("Form", "BOQ", boq.name);
					}),
			__("Create")
		);
	},
});
