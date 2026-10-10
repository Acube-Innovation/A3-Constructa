// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("WBS", {
	setup(frm) {
		frm.set_query("parent_wbs", () => ({
			filters: { is_group: 1, ...(frm.doc.project ? { project: frm.doc.project } : {}) },
		}));
		frm.set_query("boq", () => ({
			filters: { docstatus: ["<", 2], ...(frm.doc.project ? { project: frm.doc.project } : {}) },
		}));
	},

	refresh(frm) {
		setup_boq_line_picker(frm);
	},

	boq(frm) {
		frm.set_value("boq_item", "");
		setup_boq_line_picker(frm);
	},
});

// boq_item stores a BOQ Item row name, which means nothing on its own, so the
// field offers the BOQ's lines as "Line 3 · FIN-POR-600 · 1,000 m²" and keeps
// the row name.
function setup_boq_line_picker(frm) {
	const field = frm.fields_dict.boq_item;
	if (!field || !field.$input) return;
	const input = field.$input.get(0);

	if (!frm.doc.boq) {
		frm.boq_lines = [];
		return;
	}

	frappe
		.xcall("a3_constructa.a3_constructa.doctype.wbs.wbs.get_boq_lines", { boq: frm.doc.boq })
		.then((lines) => {
			frm.boq_lines = lines.map((l) => ({
				value: l.name,
				label: `${__("Line {0}", [l.idx])} · ${l.item_code} · ${format_number(l.boq_qty, null, 0)} ${l.uom || ""}${
					l.wbs ? " · " + l.wbs : ""
				}`,
			}));
			if (!field.awesomplete) {
				field.awesomplete = new Awesomplete(input, {
					minChars: 0,
					maxItems: 99,
					autoFirst: true,
					list: [],
					filter: () => true,
					sort: false,
					item: (item) =>
						$(`<li>${frappe.utils.escape_html(item.label)}</li>`).get(0),
					replace: (item) => {
						input.value = item.value;
					},
				});
				$(input).on("focus", () => {
					field.awesomplete.list = frm.boq_lines || [];
					field.awesomplete.evaluate();
				});
				$(input).on("awesomplete-selectcomplete", (e) => {
					frm.set_value("boq_item", e.originalEvent.text.value);
				});
			}
			field.awesomplete.list = frm.boq_lines;
			show_boq_line_label(frm);
		});
}

function show_boq_line_label(frm) {
	const line = (frm.boq_lines || []).find((l) => l.value === frm.doc.boq_item);
	frm.set_df_property(
		"boq_item",
		"description",
		line ? line.label : __("Click the field to pick one of the BOQ's lines.")
	);
}

frappe.ui.form.on("WBS", "boq_item", (frm) => show_boq_line_label(frm));
