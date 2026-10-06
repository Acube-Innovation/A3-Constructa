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

// Catalogue 2.4: the client's bill, from a spreadsheet.
frappe.ui.form.on("BOQ", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Import lines"), () => import_lines(frm));
		if (frm.doc.boq_stage === "Tender") {
			frm.set_intro(
				__("Tender BOQ: the client's bill, priced for the bid. It is sent through a Quotation and becomes the Contract BOQ once won; it is never approved as a budget."),
				"blue"
			);
		}
	},
});

function import_lines(frm) {
	let checked = [];
	const dialog = new frappe.ui.Dialog({
		title: __("Import BOQ lines"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "help",
				options: `<p class="text-muted">${__(
					"An .xlsx or .csv with the headings <b>boq_ref, cost_head, description, uom, qty</b> and, if known, <b>item_code</b>. Quantities and units are kept as the bill states them. If any row fails, nothing is imported."
				)} <a href="/api/method/a3_constructa.api.boq_import.download_template">${__("Download the template")}</a></p>`,
			},
			{ fieldtype: "Attach", fieldname: "file", label: __("Bill (xlsx or csv)"), reqd: 1,
			  onchange: () => preview(dialog.get_value("file")) },
			{ fieldtype: "HTML", fieldname: "result" },
		],
		primary_action_label: __("Append lines"),
		primary_action() {
			if (!checked.length) {
				frappe.msgprint(__("Upload a bill that passes the checks first."));
				return;
			}
			checked.forEach((row) => {
				const child = frm.add_child("items", {
					boq_ref: row.boq_ref,
					cost_head: row.cost_head,
					description: row.description,
					uom: row.uom,
					boq_qty: row.boq_qty,
				});
				if (row.item_code) {
					// Setting the item fetches its name; the bill's own description is kept.
					frappe.model.set_value(child.doctype, child.name, "item_code", row.item_code).then(() =>
						frappe.model.set_value(child.doctype, child.name, { description: row.description, uom: row.uom })
					);
				}
			});
			frm.refresh_field("items");
			frm.dirty();
			frappe.show_alert({ message: __("{0} lines appended. Save the BOQ to keep them.", [checked.length]), indicator: "green" });
			dialog.hide();
		},
	});
	dialog.get_primary_btn().prop("disabled", true);

	function preview(file_url) {
		checked = [];
		dialog.get_primary_btn().prop("disabled", true);
		const area = dialog.fields_dict.result.$wrapper;
		if (!file_url) return area.empty();
		area.html(`<p class="text-muted">${__("Checking the bill...")}</p>`);
		frappe.xcall("a3_constructa.api.boq_import.read_lines", { file_url }).then((r) => {
			if (r.errors.length) {
				area.html(
					`<div class="alert alert-danger"><b>${__("Nothing imported. Fix these rows and upload again:")}</b><ul>${r.errors
						.map((e) => `<li>${frappe.utils.escape_html(e)}</li>`)
						.join("")}</ul></div>`
				);
				return;
			}
			checked = r.rows;
			const shown = r.rows.slice(0, 50);
			area.html(`
				<p><b>${__("{0} lines ready to append.", [r.rows.length])}</b>${
					r.rows.length > shown.length ? " " + __("Showing the first {0}.", [shown.length]) : ""
				}</p>
				<div class="table-responsive"><table class="table table-bordered table-sm">
					<thead><tr><th>${__("Row")}</th><th>${__("Ref")}</th><th>${__("Cost Head")}</th><th>${__("Description")}</th>
					<th class="text-right">${__("Qty")}</th><th>${__("UOM")}</th><th>${__("Item")}</th></tr></thead>
					<tbody>${shown
						.map(
							(l) => `<tr><td>${l.sheet_row}</td><td>${frappe.utils.escape_html(l.boq_ref || "")}</td>
							<td>${frappe.utils.escape_html(l.cost_head)}</td><td>${frappe.utils.escape_html(l.description)}</td>
							<td class="text-right">${format_number(l.boq_qty, null, l.boq_qty % 1 ? 3 : 0)}</td><td>${frappe.utils.escape_html(l.uom)}</td>
							<td>${frappe.utils.escape_html(l.item_code || "")}</td></tr>`
						)
						.join("")}</tbody></table></div>`);
			dialog.get_primary_btn().prop("disabled", false);
		});
	}
	dialog.show();
}

// Catalogue 2.5: each line's rate is built up on its Estimate Sheet.
frappe.ui.form.on("BOQ", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Estimate Sheets"), () =>
			frappe.set_route("List", "Estimate Sheet", { boq: frm.doc.name })
		, __("View"));
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Re-price sheets"), () =>
				frappe.xcall("a3_constructa.a3_constructa.doctype.estimate_sheet.estimate_sheet.reprice_sheets", { boq: frm.doc.name })
					.then((changes) => {
						frm.reload_doc();
						if (!changes.length) {
							frappe.msgprint(__("Every sheet already uses the current prices."));
							return;
						}
						frappe.msgprint({
							title: __("{0} sheets re-priced", [changes.length]),
							message: `<table class="table table-sm"><thead><tr><th>${__("Line")}</th><th class="text-right">${__("Unit cost before")}</th><th class="text-right">${__("After")}</th></tr></thead><tbody>${changes
								.map((c) => `<tr><td>${frappe.utils.escape_html(c.boq_ref || c.sheet)}</td><td class="text-right">${format_currency(c.before, frm.doc.currency)}</td><td class="text-right">${format_currency(c.after, frm.doc.currency)}</td></tr>`)
								.join("")}</tbody></table>`,
						});
					})
			);
		}
	},
});

frappe.ui.form.on("BOQ Item", {
	open_estimate(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (frm.is_dirty() || row.__islocal) {
			frappe.msgprint(__("Save the BOQ first, so the line can be priced."));
			return;
		}
		if (row.is_allowance) {
			frappe.msgprint(__("An allowance is a sum, not built up from resources."));
			return;
		}
		frappe
			.xcall("a3_constructa.a3_constructa.doctype.estimate_sheet.estimate_sheet.open_for_line", { boq: frm.doc.name, boq_item: row.name })
			.then((name) => frappe.set_route("Form", "Estimate Sheet", name));
	},
});
