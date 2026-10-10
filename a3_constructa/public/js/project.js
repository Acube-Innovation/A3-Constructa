// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 6.11: handover and the defects liability period.
const HO = "a3_constructa.overrides.handover";

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;
		// A new BOQ for this project; its client, currency and award are filled from it.
		frm.add_custom_button(__("BOQ"), () => frappe.new_doc("BOQ", { project: frm.doc.name, boq_stage: "Budget" }), __("Create"));
		const group = __("Handover");
		const can_hand_over = frappe.user.has_role(["Constructa Project Manager", "A3 Constructa Admin", "System Manager"]);
		frm.add_custom_button(__("Snag Lists"), () => frappe.set_route("List", "Snag List", { project: frm.doc.name }), group);
		if (!frm.doc.practical_completion_date) {
			if (can_hand_over) frm.add_custom_button(__("Issue practical completion"), () => practical_completion(frm), group);
			return;
		}
		frm.add_custom_button(__("Report defect"), () =>
			frappe.new_doc("Warranty Claim", { project: frm.doc.name, customer: frm.doc.customer, company: frm.doc.company,
				complaint_date: frappe.datetime.get_today(), status: "Open" }), group);
		frm.add_custom_button(__("Defects (warranty claims)"), () => frappe.set_route("List", "Warranty Claim", { project: frm.doc.name }), group);
		if (can_hand_over && frm.doc.dlp_end_date && frm.doc.dlp_end_date <= frappe.datetime.get_today()) {
			frm.add_custom_button(__("End of DLP"), () => end_dlp(frm), group);
		}
	},
});

function practical_completion(frm) {
	frappe.prompt(
		[{ fieldname: "date", label: __("Practical completion on"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 }],
		({ date }) => frappe.xcall(`${HO}.issue_practical_completion`, { project: frm.doc.name, date }).then((r) => {
			const lines = [__("Practical completion {0}; defects liability period to {1}.",
				[frappe.datetime.str_to_user(r.practical_completion_date), frappe.datetime.str_to_user(r.dlp_end_date)])];
			lines.push(r.retention_release ? __("Retention release (first half) drafted: {0}, for finance to submit.",
				[`<a href="/app/sales-invoice/${r.retention_release}">${r.retention_release}</a>`]) : r.note);
			frappe.msgprint({ title: __("Practical completion"), message: lines.join("<br>"), indicator: "green" });
			frm.reload_doc();
		}).catch(() => {}), // a refusal (snags outstanding) is already shown by the server's message
		__("Issue practical completion"), __("Issue"));
}

function end_dlp(frm) {
	frappe.xcall(`${HO}.end_dlp`, { project: frm.doc.name }).then((r) => {
		const esc = frappe.utils.escape_html;
		const rows = r.surplus.map((s) => `<tr><td>${esc(s.item_name)}</td><td>${esc(s.warehouse)}</td><td class="text-right">${s.actual_qty} ${esc(s.stock_uom)}</td><td class="text-right">${format_currency(s.stock_value)}</td></tr>`).join("");
		const claims = r.open_claims.map((c) => `<li><a href="/app/warranty-claim/${c.name}">${c.name}</a> (${esc(c.status)})</li>`).join("");
		const d = new frappe.ui.Dialog({
			title: __("End of the defects liability period"),
			size: "large",
			fields: [
				{ fieldtype: "HTML", options: `
					<p>${r.retention_release ? __("Retention release (second half): {0}, a draft for finance to submit.", [`<a href="/app/sales-invoice/${r.retention_release}">${r.retention_release}</a>`]) : esc(r.note || "")}</p>
					${claims ? `<p class="text-danger">${__("Defects still open")}:</p><ul>${claims}</ul>` : ""}
					<p><b>${__("Surplus stock in the project's stores")}</b></p>
					${rows ? `<table class="table table-bordered"><thead><tr><th>${__("Item")}</th><th>${__("Store")}</th><th class="text-right">${__("Qty")}</th><th class="text-right">${__("Value")}</th></tr></thead><tbody>${rows}</tbody></table>`
						: `<p class="text-muted">${__("Nothing left in the project's stores.")}</p>`}` },
				...(rows ? [{ fieldname: "to_warehouse", label: __("Return to"), fieldtype: "Link", options: "Warehouse", reqd: 1,
					get_query: () => ({ filters: { company: frm.doc.company, is_group: 0 } }) }] : []),
			],
			primary_action_label: rows ? __("Draft Site Material Return") : __("Close"),
			primary_action(values) {
				if (!rows) return d.hide();
				frappe.xcall(`${HO}.return_surplus`, { project: frm.doc.name, to_warehouse: values.to_warehouse })
					.then((name) => { d.hide(); frappe.set_route("Form", "Stock Entry", name); }).catch(() => {});
			},
		});
		d.show();
	}).catch(() => {});
}
