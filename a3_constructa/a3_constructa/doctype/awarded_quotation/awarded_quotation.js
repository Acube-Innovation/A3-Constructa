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

// Catalogue 3.7: one step from the award to a running job.
frappe.ui.form.on("Awarded Quotation", {
	refresh(frm) {
		if (frm.is_new() || !["Awarded", "In Progress"].includes(frm.doc.status)) return;
		const button = frm.add_custom_button(__("Hand over to project"), () => hand_over(frm));
		if (frm.doc.status === "Awarded" && !frm.doc.project) button.addClass("btn-primary");
	},
});

function hand_over(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the award first."));
		return;
	}
	frappe.xcall("a3_constructa.api.award_handover.get_handover_plan", { award: frm.doc.name }).then((plan) => {
		const will = (exists, made) => (exists ? __("Already there: {0}, will be linked", [exists]) : made);
		const budget = plan.tender_boqs.length
			? plan.tender_boqs.map((t) => will(plan.budget_boqs[t], __("A budget BOQ, revision 0, will be copied from {0}", [t]))).join("<br>")
			: __("No tender BOQ on the components, so no budget BOQ is copied.");
		const d = new frappe.ui.Dialog({
			title: __("Hand over {0} to project", [frm.doc.name]),
			size: "large",
			fields: [
				{ fieldtype: "HTML", fieldname: "intro",
				  options: `<p class="text-muted">${__("Each step links what already exists and creates only what is missing.")}</p>` },
				{ fieldtype: "Section Break", label: __("a. Project") },
				{ fieldtype: "HTML", fieldname: "project_note",
				  options: `<p>${plan.project ? __("Already linked: {0}", [plan.project]) : __("A new project will be created, unless you pick one.")}</p>` },
				{ fieldtype: "Link", fieldname: "project", label: __("Use Existing Project"), options: "Project",
				  default: plan.project, read_only: plan.project ? 1 : 0,
				  get_query: () => ({ filters: { company: plan.company } }) },
				{ fieldtype: "Data", fieldname: "project_name", label: __("New Project Name"), default: plan.project_name,
				  depends_on: "eval:!doc.project" },
				{ fieldtype: "Link", fieldname: "cost_center", label: __("Cost Centre"), options: "Cost Center",
				  default: plan.cost_center, depends_on: "eval:!doc.project",
				  get_query: () => ({ filters: { company: plan.company, is_group: 0 } }) },
				{ fieldtype: "Column Break" },
				{ fieldtype: "Date", fieldname: "start_date", label: __("Start Date"), default: plan.start_date, reqd: 1 },
				{ fieldtype: "Date", fieldname: "end_date", label: __("Completion Date"), default: plan.end_date, reqd: 1 },
				{ fieldtype: "Section Break", label: __("b. Sales Order") },
				{ fieldtype: "Check", fieldname: "make_sales_order", label: __("Sales Order for the award"), default: 1 },
				{ fieldtype: "Select", fieldname: "sales_order_lines", label: __("Lines"),
				  options: ["Per component", "Per BOQ line"], default: "Per component",
				  description: plan.sales_order ? __("Already there: {0}, will be linked", [plan.sales_order])
					: __("Components: {0}. BOQ lines: {1}. The order is left in draft.", [plan.components, plan.boq_lines]) },
				{ fieldtype: "Section Break", label: __("c. Budget BOQ") },
				{ fieldtype: "Check", fieldname: "make_budget_boq", label: __("Budget BOQ, revision 0"), default: 1,
				  description: budget },
				{ fieldtype: "Section Break", label: __("d. Attachments and notes") },
				{ fieldtype: "Check", fieldname: "copy_notes", label: __("Copy to the project"), default: 1,
				  description: __("{0} attachments and {1} notes on the quotation and opportunity", [plan.attachments, plan.notes]) },
			],
			primary_action_label: __("Hand over"),
			primary_action(values) {
				frappe
					.xcall("a3_constructa.api.award_handover.hand_over", { award: frm.doc.name, ...values })
					.then((done) => {
						d.hide();
						frm.reload_doc();
						const list = (items) => items.map((x) => `<li>${frappe.utils.escape_html(x)}</li>`).join("");
						frappe.msgprint({
							title: __("Handed over"),
							indicator: "green",
							message: `${done.created.length ? `<p><b>${__("Created")}</b></p><ul>${list(done.created)}</ul>` : ""}${
								done.linked.length ? `<p><b>${__("Already there, linked")}</b></p><ul>${list(done.linked)}</ul>` : ""}`,
						});
					});
			},
		});
		d.show();
	});
}
