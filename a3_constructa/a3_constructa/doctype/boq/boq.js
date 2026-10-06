// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("BOQ Item", {
	// draws_from_allowance stores an allowance row's name; the row form offers
	// this BOQ's saved allowance lines by their description instead.
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const field = frm.cur_grid?.grid_form?.fields_dict?.draws_from_allowance;
		if (!field || row.is_allowance) return;
		show_allowance_label(frm, row, field);
		if (!field.$input || field.allowance_picker) return;
		const input = field.$input.get(0);
		const options = allowance_options(frm, row);
		const aw = (field.allowance_picker = new Awesomplete(input, {
			minChars: 0,
			maxItems: 50,
			autoFirst: true,
			sort: false,
			filter: () => true,
			list: options,
			item: (item) => $(`<li>${frappe.utils.escape_html(item.label)}</li>`).get(0),
			replace: (item) => {
				input.value = item.value;
			},
		}));
		$(input).on("focus", () => {
			aw.list = allowance_options(frm, row);
			aw.evaluate();
		});
		$(input).on("awesomplete-selectcomplete", (e) => {
			frappe.model.set_value(cdt, cdn, "draws_from_allowance", e.originalEvent.text.value);
		});
	},

	draws_from_allowance(frm, cdt, cdn) {
		const field = frm.cur_grid?.grid_form?.fields_dict?.draws_from_allowance;
		if (field) show_allowance_label(frm, locals[cdt][cdn], field);
	},

	is_allowance(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.is_allowance) {
			frappe.model.set_value(cdt, cdn, { item_code: "", boq_qty: 0, rate: 0, draws_from_allowance: "" });
		}
	},

	boq_qty: (frm, cdt, cdn) => set_amount(cdt, cdn),
	rate: (frm, cdt, cdn) => set_amount(cdt, cdn),
});

function set_amount(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.is_allowance) {
		frappe.model.set_value(cdt, cdn, "amount", flt(row.boq_qty) * flt(row.rate));
	}
}

function allowance_options(frm, row) {
	return (frm.doc.items || [])
		.filter((r) => r.is_allowance && r.name !== row.name && !r.name.startsWith("new-"))
		.map((r) => ({
			value: r.name,
			label: `${__("Line {0}", [r.idx])} · ${r.description || ""} · ${format_currency(r.amount, frm.doc.currency)}${
				r.allowance_remaining != null ? " · " + __("{0} left", [format_currency(r.allowance_remaining, frm.doc.currency)]) : ""
			}`,
		}));
}

function show_allowance_label(frm, row, field) {
	const match = allowance_options(frm, row).find((o) => o.value === row.draws_from_allowance);
	field.set_description(
		match ? match.label : __("Click to pick an allowance line of this BOQ. Save the BOQ first if the allowance line is new.")
	);
}
