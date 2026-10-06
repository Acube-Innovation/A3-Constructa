// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Quotation from a tender BOQ (catalogue 2.7): margin, margin approval, re-pricing
// from the BOQ, and Set as Lost with the price the job went for.

// ERPNext's Set as Lost dialog, with one more field: the winning competitor's price.
frappe.ui.form.off("Quotation", "set_as_lost_dialog");
frappe.ui.form.on("Quotation", {
	set_as_lost_dialog(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Set as Lost"),
			fields: [
				{ fieldtype: "Table MultiSelect", label: __("Lost Reasons"), fieldname: "lost_reason",
				  options: "Quotation Lost Reason Detail", reqd: 1 },
				{ fieldtype: "Table MultiSelect", label: __("Competitors"), fieldname: "competitors",
				  options: "Competitor Detail" },
				{ fieldtype: "Currency", label: __("Winning Competitor Price"), fieldname: "competitor_price",
				  options: frm.doc.currency,
				  description: __("Our price was {0}. Leave blank if the client did not say.",
					[format_currency(frm.doc.grand_total, frm.doc.currency)]) },
				{ fieldtype: "Small Text", label: __("Detailed Reason"), fieldname: "detailed_reason" },
			],
			primary_action_label: __("Declare Lost"),
			primary_action(values) {
				frappe
					.xcall("a3_constructa.overrides.quotation.declare_lost", {
						quotation: frm.doc.name,
						lost_reasons: values.lost_reason,
						competitors: values.competitors || [],
						detailed_reason: values.detailed_reason,
						competitor_price: values.competitor_price,
					})
					.then(() => {
						dialog.hide();
						frm.reload_doc();
					});
			},
		});
		dialog.show();
	},

	refresh(frm) {
		show_margin_state(frm);
		const editable = !["Pending Management Approval"].includes(frm.doc.workflow_state);
		if (frm.doc.boq && frm.doc.docstatus === 0 && !frm.is_new() && editable) {
			frm.add_custom_button(__("Update from BOQ"), () => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save the quotation first."));
					return;
				}
				frappe
					.xcall("a3_constructa.overrides.quotation.update_from_boq", { quotation: frm.doc.name })
					.then((r) => {
						frm.reload_doc();
						frappe.show_alert({
							message: __("Lines updated from {0}: {1} → {2}, margin {3}%", [
								frm.doc.boq,
								format_currency(r.before, frm.doc.currency),
								format_currency(r.after, frm.doc.currency),
								flt(r.margin_percent, 2),
							]),
							indicator: "green",
						});
					});
			});
		}
	},
});

function show_margin_state(frm) {
	if (!frm.doc.boq) return;
	const margin = `${flt(frm.doc.margin_percent, 2)}%`;
	const state = frm.doc.workflow_state;
	if (frm.doc.docstatus === 1 && state === "Approved") {
		frm.set_intro(__("Management approved this price at a {0} margin, below the minimum.", [margin]), "blue");
		return;
	}
	if (frm.doc.docstatus !== 0) return;
	if (state === "Pending Management Approval") {
		frm.set_intro(__("Waiting for management approval: the margin is {0}, below the minimum.", [margin]), "orange");
		frm.page.set_indicator(__(state), "orange");
	} else if (state === "Rejected") {
		frm.set_intro(__("Management rejected this price. Revise it, then send it again."), "red");
		frm.page.set_indicator(__(state), "red");
	} else if (frm.doc.below_minimum_margin) {
		frm.set_intro(
			__("The margin is {0}, below the minimum. Use Submit for Approval: management approves it before it goes to the client.", [margin]),
			"orange"
		);
	}
}
