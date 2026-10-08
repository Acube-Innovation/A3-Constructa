// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tender Clarification", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.set_intro(
			frm.doc.status === "Open"
				? __("Query {0}: waiting for the client's answer since {1}.", [frm.doc.query_no, frappe.datetime.str_to_user(frm.doc.raised_on)])
				: frm.doc.price_impact
				? __("Answered with a price impact: revisit the estimate.")
				: "",
			frm.doc.status === "Open" ? "orange" : "blue"
		);
	},
});
