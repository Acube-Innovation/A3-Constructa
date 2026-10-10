// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 4.1: an awarded order carries the contract. Its terms come from the
// award and only an Accounts Manager may change them here; each line names the
// BOQ line it bills and its WBS.
const A3_TERMS = ["contract_type", "retention_percent", "retention_cap_percent", "advance_percent", "advance_recovery_percent", "defects_liability_months"];

frappe.ui.form.on("Sales Order", {
	setup(frm) {
		frm.set_query("boq", "items", () => ({
			filters: frm.doc.awarded_quotation ? { awarded_quotation: frm.doc.awarded_quotation } : {},
		}));
		frm.set_query("wbs", "items", () => ({ filters: frm.doc.project ? { project: frm.doc.project, status: "Active" } : {} }));
	},

	refresh(frm) {
		const locked = !frappe.user.has_role("Accounts Manager");
		A3_TERMS.forEach((field) => frm.set_df_property(field, "read_only", locked && frm.doc.awarded_quotation ? 1 : 0));
		if (frm.doc.awarded_quotation && frm.doc.docstatus === 0) {
			const missing = (frm.doc.items || []).filter((row) => !(row.boq && row.boq_item && row.wbs)).map((row) => row.idx);
			if (missing.length) {
				frm.set_intro(
					missing.length === 1
						? __("Row {0} still needs its BOQ line and WBS before this awarded order can be submitted.", [missing[0]])
						: __("Rows {0} still need their BOQ line and WBS before this awarded order can be submitted.", [missing.join(", ")]),
					"orange"
				);
			}
		}
	},

	awarded_quotation(frm) {
		if (!frm.doc.awarded_quotation) return;
		frappe.db.get_value("Awarded Quotation", frm.doc.awarded_quotation, ["project", ...A3_TERMS]).then(({ message }) => {
			if (!message) return;
			A3_TERMS.forEach((field) => frm.set_value(field, message[field]));
			if (message.project && !frm.doc.project) frm.set_value("project", message.project);
		});
	},
});
