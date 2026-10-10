// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("WBS Allocation", {
	setup(frm) {
		frm.set_query("boq", () => ({
			filters: { docstatus: 1, ...(frm.doc.project ? { project: frm.doc.project } : {}) },
		}));
		frm.set_query("wbs", () => ({
			filters: { status: "Active", ...(frm.doc.project ? { project: frm.doc.project } : {}) },
		}));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.boq) {
			frm.add_custom_button(__("Get Lines from BOQ"), () => pick_boq_lines(frm));
		}
	},

	boq(frm) {
		frm.trigger("refresh");
	},
});

frappe.ui.form.on("WBS Allocation Item", {
	allocated_qty: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => set_amount(frm, cdt, cdn),
});

function set_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.is_allowance) {
		frappe.model.set_value(cdt, cdn, "allocated_amount", flt(row.allocated_qty) * flt(row.rate));
	}
}

// Offers the BOQ lines that still have something left to allocate, with that
// balance filled in, so the 100% rule is easy to keep.
function pick_boq_lines(frm) {
	frappe
		.xcall("a3_constructa.a3_constructa.doctype.wbs_allocation.wbs_allocation.get_lines_to_allocate", {
			boq: frm.doc.boq,
			allocation: frm.is_new() ? null : frm.doc.name,
		})
		.then((lines) => {
			const taken = new Set((frm.doc.items || []).map((r) => r.boq_item));
			lines = lines.filter((l) => !taken.has(l.name));
			if (!lines.length) {
				frappe.msgprint(__("Every line of {0} is already fully allocated or on this allocation.", [frm.doc.boq]));
				return;
			}
			const currency = frappe.boot.sysdefaults.currency;
			const dialog = new frappe.ui.Dialog({
				title: __("Lines of {0} left to allocate", [frm.doc.boq]),
				size: "large",
				fields: [
					{
						fieldname: "lines",
						fieldtype: "Table",
						cannot_add_rows: true,
						in_place_edit: true,
						data: lines.map((l) => ({
							boq_item: l.name,
							line: `${l.idx} · ${l.is_allowance ? l.description : l.item_code}`,
							left: l.is_allowance
								? format_currency(l.free, currency)
								: `${format_number(l.free, null, 2)} ${l.uom || ""}`,
							allocate: l.free,
							is_allowance: l.is_allowance,
							item_code: l.item_code,
							cost_code: l.cost_code,
							rate: l.approved_rate,
						})),
						fields: [
							{ fieldname: "line", label: __("BOQ Line"), fieldtype: "Data", read_only: 1, in_list_view: 1, columns: 4 },
							{ fieldname: "left", label: __("Left"), fieldtype: "Data", read_only: 1, in_list_view: 1, columns: 3 },
							{ fieldname: "allocate", label: __("Allocate (qty, or amount for an allowance)"), fieldtype: "Float", in_list_view: 1, columns: 3 },
						],
					},
				],
				primary_action_label: __("Add Selected"),
				primary_action() {
					const chosen = dialog.fields_dict.lines.grid.get_selected_children();
					if (!chosen.length) {
						frappe.show_alert({ message: __("Tick the lines to add."), indicator: "orange" });
						return;
					}
					chosen.forEach((c) => {
						frm.add_child("items", {
							boq_item: c.boq_item,
							is_allowance: c.is_allowance,
							item_code: c.item_code,
							cost_code: c.cost_code,
							rate: c.is_allowance ? 0 : c.rate,
							allocated_qty: c.is_allowance ? 0 : c.allocate,
							allocated_amount: c.is_allowance ? c.allocate : flt(c.allocate) * flt(c.rate),
						});
					});
					frm.refresh_field("items");
					frm.dirty();
					dialog.hide();
				},
			});
			dialog.show();
		});
}
