// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Awarded Quotation", {
	setup(frm) {
		// A component's BOQ and cost head belong to the award's project.
		const same_project = () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} });
		frm.set_query("boq", "components", same_project);
		frm.set_query("cost_head", "components", same_project);
		frm.set_query("quotation", () => ({
			filters: frm.doc.customer ? { quotation_to: "Customer", party_name: frm.doc.customer } : {},
		}));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},

	// The award is priced in its company's currency unless someone chooses otherwise.
	company(frm) {
		if (!frm.doc.company) return;
		frappe.db.get_value("Company", frm.doc.company, "default_currency").then(({ message }) => {
			if (message && message.default_currency) frm.set_value("currency", message.default_currency);
		});
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const create = (doctype, values) =>
			frm.add_custom_button(__(doctype), () => frappe.new_doc(doctype, values), __("Create"));

		create("BOQ", { project: frm.doc.project, awarded_quotation: frm.doc.name, currency: frm.doc.currency });
		create("Variation Order", { awarded_quotation: frm.doc.name });
		create("Deliverable", { awarded_quotation: frm.doc.name });
		frm.add_custom_button(
			__("Material Request"),
			() => {
				// material_request.js opens Get Items From > BOQ for this award.
				frappe.flags.a3_request_from_award = frm.doc.name;
				frappe.new_doc("Material Request", { material_request_type: "Purchase", company: frm.doc.company });
			},
			__("Create")
		);

		frm.add_custom_button(
			__("Procurement"),
			() => frappe.set_route("award-procurement", frm.doc.name),
			__("View")
		);
	},
});

frappe.ui.form.on("Awarded Quotation Component", {
	qty: update_component_amount,
	rate: update_component_amount,
	components_remove: update_contract_value,
});

// The server recomputes both on save; this only keeps the form current while typing.
function update_component_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	update_contract_value(frm);
}

function update_contract_value(frm) {
	const total = (frm.doc.components || []).reduce((sum, row) => sum + flt(row.amount), 0);
	frm.set_value("contract_value", total);
}
