// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Estimate Sheet", {
	refresh(frm) {
		// A block body, so the button gets no jQuery promise back (it expects one with .finally).
		frm.add_custom_button(__("Fetch prices"), () => {
			frm.call("fetch_prices").then(() => {
				frm.dirty();
				frm.refresh_fields();
				frappe.show_alert({ message: __("Prices fetched. Save to write the unit cost to the BOQ line."), indicator: "green" });
			});
		});
		if (frm.doc.boq) {
			frm.add_custom_button(__("Back to BOQ"), () => frappe.set_route("Form", "BOQ", frm.doc.boq));
		}
		frm.set_intro(
			__("Material, subcontract and other: qty per BOQ unit × (1 + wastage) × rate. Labour and equipment: day rate ÷ output per day."),
			"blue"
		);
	},
});

frappe.ui.form.on("Estimate Resource", {
	resource_type: recalc,
	qty_per_unit: recalc,
	wastage_percent: recalc,
	output_per_day: recalc,
	rate(frm, cdt, cdn) {
		// A rate typed by hand is kept by "Fetch prices".
		frappe.model.set_value(cdt, cdn, { rate_source: "Manual", source_doctype: null, source_reference: null });
		recalc(frm);
	},
	resources_remove: recalc,
});

function recalc(frm) {
	let total = 0;
	(frm.doc.resources || []).forEach((r) => {
		const per_day = ["Labour", "Equipment"].includes(r.resource_type);
		r.cost_per_unit = per_day
			? (flt(r.output_per_day) ? flt(r.rate) / flt(r.output_per_day) : 0)
			: flt(r.qty_per_unit) * (1 + (r.resource_type === "Material" ? flt(r.wastage_percent) : 0) / 100) * flt(r.rate);
		total += r.cost_per_unit;
	});
	frm.refresh_field("resources");
	frm.set_value("unit_cost", total);
	frm.set_value("total_cost", total * flt(frm.doc.boq_qty));
}
