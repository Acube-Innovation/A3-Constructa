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

// A sheet prices one BOQ line. Started from the list, it asks which line; opened
// from the line (or after saving) it is already set.
const SHEET_EST = "a3_constructa.api.estimate_import";
frappe.ui.form.on("Estimate Sheet", {
	refresh(frm) {
		if (frm.is_new() && !frm.doc.boq_item) {
			frm.set_intro(__("Pick the BOQ, then the line this sheet prices."), "orange");
			if (frm.doc.boq) pick_line(frm);
		}
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Import resources"), () => import_resources(frm));
		}
	},
	boq(frm) {
		if (frm.is_new() && frm.doc.boq && !frm.doc.boq_item) pick_line(frm);
	},
});

function pick_line(frm) {
	// refresh and the BOQ trigger both land here for a sheet started with its BOQ: ask once.
	if (frm.__picking === frm.doc.name + frm.doc.boq) return;
	frm.__picking = frm.doc.name + frm.doc.boq;
	frappe.xcall(`${SHEET_EST}.boq_lines`, { boq: frm.doc.boq }).then((lines) => {
		if (!lines.length) {
			frappe.msgprint(__("{0} has no saved lines to price. Add lines to the BOQ and save it first.", [frm.doc.boq]));
			return;
		}
		const label = (l) => `${l.boq_ref || __("Line {0}", [l.idx])} · ${(l.description || l.item_name || "").slice(0, 70)}${
			l.estimate_sheet ? " · " + __("has {0}", [l.estimate_sheet]) : ""}`;
		const d = new frappe.ui.Dialog({
			title: __("Which line of {0}?", [frm.doc.boq]),
			fields: [{ fieldtype: "Select", fieldname: "line", label: __("BOQ line"), reqd: 1,
				options: lines.map((l) => ({ value: l.name, label: label(l) })) }],
			primary_action_label: __("Open its sheet"),
			primary_action({ line }) {
				d.hide();
				// The line's own sheet: opened if it has one, else created for it.
				frappe.xcall("a3_constructa.a3_constructa.doctype.estimate_sheet.estimate_sheet.open_for_line", { boq: frm.doc.boq, boq_item: line })
					.then((name) => frappe.set_route("Form", "Estimate Sheet", name));
			},
		});
		d.show();
	});
}

function import_resources(frm) {
	let checked = null;
	const dialog = new frappe.ui.Dialog({
		title: __("Import resources"),
		size: "large",
		fields: [
			{ fieldtype: "HTML", fieldname: "help", options: `<p class="text-muted">${__(
				"An .xlsx or .csv with the columns <b>resource_type</b>, <b>item_code</b> or <b>description</b>, <b>uom</b>, <b>qty_per_unit</b>, <b>wastage_percent</b>, <b>output_per_day</b>, <b>rate</b> (blank on an item: the price is fetched). A <b>boq_ref</b> column is optional; rows for other lines are left out, so the BOQ-wide file works here too."
			)}</p>` },
			{ fieldtype: "Attach", fieldname: "file", label: __("Resources (xlsx or csv)"), reqd: 1,
			  options: { restrictions: { allowed_file_types: [".xlsx", ".csv"] } },
			  onchange: () => check(dialog.get_value("file")) },
			{ fieldtype: "Check", fieldname: "replace", label: __("Replace the resources this sheet has"), default: 1 },
			{ fieldtype: "HTML", fieldname: "result" },
		],
		primary_action_label: __("Add resources"),
		primary_action({ replace }) {
			if (!checked) return frappe.msgprint(__("Upload a file that passes the checks first."));
			if (replace) frm.clear_table("resources");
			Object.values(checked.lines)[0].forEach((row) => {
				const r = Object.assign({}, row);
				delete r.sheet_row;
				frm.add_child("resources", r);
			});
			dialog.hide();
			// Items with no rate get their price, as "Fetch prices" would; then save.
			frm.call("fetch_prices").then(() => frm.save());
		},
	});
	dialog.set_secondary_action_label(__("Download template"));
	dialog.set_secondary_action(() => window.open(`/api/method/${SHEET_EST}.download_template?boq=${encodeURIComponent(frm.doc.boq)}`));
	dialog.get_primary_btn().prop("disabled", true);
	function check(file_url) {
		checked = null;
		dialog.get_primary_btn().prop("disabled", true);
		const area = dialog.fields_dict.result.$wrapper;
		if (!file_url) return area.empty();
		area.html(`<p class="text-muted">${__("Checking...")}</p>`);
		frappe.xcall(`${SHEET_EST}.read_resources`, { file_url, boq: frm.doc.boq, boq_item: frm.doc.boq_item }).then((r) => {
			r.replaces = [];
			area.html(a3_constructa.resources_summary(r, frm.doc.currency) +
				(r.skipped ? `<p class="text-muted">${__("{0} rows for other lines left out.", [r.skipped])}</p>` : ""));
			if (!r.errors.length) checked = r;
			dialog.get_primary_btn().prop("disabled", !checked);
		});
	}
	dialog.show();
}
