// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

const FA = "a3_constructa.a3_constructa.doctype.final_account.final_account";

frappe.ui.form.on("Final Account", {
	setup(frm) {
		frm.set_query("awarded_quotation", () => ({ filters: { status: ["in", ["Awarded", "In Progress", "On Hold", "Completed"]] } }));
	},

	refresh(frm) {
		if (frm.doc.awarded_quotation && frm.doc.award_status && frm.doc.award_status !== "Completed" && frm.doc.docstatus < 2) {
			frm.set_intro(__("{0} is {1}, not yet Completed. The final account normally follows completion.", [frm.doc.awarded_quotation, __(frm.doc.award_status)]), "orange");
		} else if (frm.is_new()) {
			frm.set_intro(__("Pick the award and save: the contract, variations, remeasure and settlement are filled in."), "blue");
		} else if (frm.doc.docstatus === 0) {
			frm.set_intro(__("Agree the adjustments with the client, then Submit: the final contract sum is fixed and the final invoice can be made."), "blue");
		}
		if (frm.doc.docstatus !== 1) return;
		if (flt(frm.doc.balance_due) > 0 && !frm.doc.final_invoice) {
			frm.add_custom_button(__("Final Invoice"), () =>
				frappe.xcall(`${FA}.make_final_invoice`, { final_account: frm.doc.name }).then((name) => frappe.set_route("Form", "Sales Invoice", name))
			, __("Create"));
		}
		if (flt(frm.doc.retention_held) - flt(frm.doc.retention_released) > 0.005 && !frm.doc.retention_release_invoice) {
			frm.add_custom_button(__("Release remaining retention"), () =>
				frappe.xcall(`${FA}.release_remaining_retention`, { final_account: frm.doc.name }).then((name) => frappe.set_route("Form", "Sales Invoice", name)));
		}
	},

	awarded_quotation(frm) {
		// The award's status is fetched with it; show the warning as soon as it arrives.
		frappe.after_ajax(() => frm.events.refresh(frm));
	},
});

frappe.ui.form.on("Final Account Adjustment", {
	amount: (frm) => adjust(frm),
	agreed: (frm) => adjust(frm),
	adjustments_remove: (frm) => adjust(frm),
});

function adjust(frm) {
	// The sum as measured, before the adjustments, stays as last calculated; the save recalculates it all.
	const measured = flt(frm.doc.final_contract_sum) - flt(frm.doc.adjustments_total);
	const total = (frm.doc.adjustments || []).filter((r) => r.agreed).reduce((s, r) => s + flt(r.amount), 0);
	frm.set_value("adjustments_total", total);
	frm.set_value("final_contract_sum", measured + total);
}
