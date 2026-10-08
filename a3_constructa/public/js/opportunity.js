// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Opportunity: Create > Tender BOQ (catalogue 2.4). Opens a new Tender BOQ with
// the opportunity, client and currency set, ready for the client's bill to be
// imported with "Import lines".
//
// Bid / No-bid (catalogue 2.2): "Score the bid" fills the six criteria with
// their starting weights; the score, what it suggests and the decision show at
// the top of the form. The Bid Decision workflow's buttons do the rest.
frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		show_bid(frm);
		if (frm.doc.bid_decision === "No-go") {
			// Decided not to bid: nothing to quote or price. ERPNext adds these in its own refresh.
			setTimeout(() => ["Quotation", "Supplier Quotation", "Request For Quotation"].forEach((label) =>
				frm.remove_custom_button(label, __("Create"))
			));
		}
		if (frm.is_new() || frm.doc.docstatus === 2 || ["Lost", "Closed"].includes(frm.doc.status)) return;
		if (frm.doc.bid_decision !== "No-go") {
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
		}
		if (!(frm.doc.bid_scores || []).length && frm.doc.bid_workflow_state !== "No-go" && frm.doc.bid_workflow_state !== "Go") {
			frm.add_custom_button(__("Score the bid"), () =>
				frappe.xcall("a3_constructa.overrides.opportunity.default_scores").then((rows) => {
					rows.forEach((row) => frm.add_child("bid_scores", row));
					frm.refresh_field("bid_scores");
					frm.scroll_to_field("bid_scores");
					frappe.show_alert({
						message: __("Score each criterion from 1 (poor) to 5 (excellent), then save."),
						indicator: "blue",
					});
				})
			);
		}
	},
});

frappe.ui.form.on("Bid Score", {
	weight: update_points,
	score: update_points,
});

function update_points(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "weighted", flt((flt(row.weight) * cint(row.score)) / 5, 2));
}

function show_bid(frm) {
	if (frm.is_new() || frm.doc.total_score === null || frm.doc.total_score === undefined) return;
	const score = format_number(frm.doc.total_score, null, 1);
	const threshold = format_number(frm.doc.bid_threshold, null, 1);
	const decision = frm.doc.bid_decision;
	let message = __("Bid score {0} of 100 against a threshold of {1}: the score suggests {2}.", [
		score,
		threshold,
		__(frm.doc.suggested_decision),
	]);
	let color = frm.doc.suggested_decision === "Go" ? "blue" : "orange";
	if (decision === "Go" || decision === "No-go") {
		message += " " + __("Decided {0} by {1} on {2}.", [
			__(decision),
			frappe.user.full_name(frm.doc.decided_by),
			frappe.datetime.str_to_user(frm.doc.decided_on),
		]);
		color = decision === "Go" ? "green" : "red";
	} else if (frm.doc.bid_workflow_state === "Awaiting Bid Decision") {
		message += " " + __("Waiting for a sales manager to confirm.");
	}
	frm.set_intro(message, color);
}
