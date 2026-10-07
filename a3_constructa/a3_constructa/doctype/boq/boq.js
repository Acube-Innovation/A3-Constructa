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

// A new BOQ takes what its project or opportunity already knows: client, currency,
// award, opportunity and measurement method. Only empty fields are filled.
frappe.ui.form.on("BOQ", {
	onload(frm) {
		if (frm.is_new() && (frm.doc.project || frm.doc.opportunity)) fill_from_sources(frm);
	},
	project(frm) {
		if (frm.doc.project && frm.doc.docstatus === 0) fill_from_sources(frm);
	},
	opportunity(frm) {
		if (frm.doc.opportunity && frm.doc.docstatus === 0) fill_from_sources(frm);
	},
});

function fill_from_sources(frm) {
	if (frm.__filling) return;
	frm.__filling = true;
	const source = frm.doc.project || frm.doc.opportunity;
	frappe
		.xcall("a3_constructa.api.boq_import.boq_defaults", { project: frm.doc.project, opportunity: frm.doc.opportunity })
		.then(async (values) => {
			if (frm.is_new() && !frm.doc.project && values.opportunity) values.boq_stage = "Tender";
			const filled = {};
			for (const [field, value] of Object.entries(values)) {
				if (field === "boq_stage" ? frm.doc.boq_stage !== value : !frm.doc[field]) filled[field] = value;
			}
			if (!Object.keys(filled).length) return;
			await frm.set_value(filled);
			frappe.show_alert({
				message: __("Filled from {0}: {1}", [source,
					Object.keys(filled).map((f) => __(frappe.meta.get_label("BOQ", f))).join(", ")]),
				indicator: "blue",
			});
		})
		.finally(() => (frm.__filling = false));
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

function download_template() {
	window.open("/api/method/a3_constructa.api.boq_import.download_template");
}

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
				)}</p><p>${__("Not sure of the layout? <b>Download template</b> (below) gives the headings and four example lines.")}</p>`,
			},
			{ fieldtype: "Attach", fieldname: "file", label: __("Bill (xlsx or csv)"), reqd: 1,
			  // The file picker then lists only spreadsheets, so the bill is easy to find.
			  options: { restrictions: { allowed_file_types: [".xlsx", ".csv"] } },
			  description: __("The template saves as boq_import_template.xlsx in your Downloads folder. You can also drag the file onto the upload box."),
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
	dialog.set_secondary_action_label(__("Download template"));
	dialog.set_secondary_action(download_template);

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

// Catalogue 2.7: a priced tender goes to the client as a Quotation.
frappe.ui.form.on("BOQ", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.boq_stage !== "Tender" || frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Quotation"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save the BOQ first, so the quotation takes its latest prices."));
				return;
			}
			frappe
				.xcall("a3_constructa.overrides.quotation.make_from_boq", { boq: frm.doc.name })
				.then((r) => {
					if (r.existing) {
						frappe.show_alert({
							message: __("{0} already quotes this BOQ. To re-price, cancel and amend it.", [r.name]),
							indicator: "blue",
						});
					}
					frappe.set_route("Form", "Quotation", r.name);
				});
		}, __("Create"));
	},
});

// Catalogue 2.5: estimate sheets for every line at once, or filled from a spreadsheet.
const BOQ_EST = "a3_constructa.api.estimate_import";
frappe.ui.form.on("BOQ", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 0) return;
		const group = __("Estimates");
		frm.add_custom_button(__("Sheets for every line"), () => {
			if (frm.is_dirty()) return frappe.msgprint(__("Save the BOQ first, so every line can be priced."));
			frappe.xcall(`${BOQ_EST}.make_sheets`, { boq: frm.doc.name }).then((r) => {
				frappe.show_alert({ message: r.made.length
					? __("{0} estimate sheets created; every line now has one.", [r.made.length])
					: __("Every line already has its estimate sheet."), indicator: "green" });
				frappe.set_route("List", "Estimate Sheet", { boq: frm.doc.name });
			});
		}, group);
		frm.add_custom_button(__("Import estimates"), () => {
			if (frm.is_dirty()) return frappe.msgprint(__("Save the BOQ first, so every line can be priced."));
			import_estimates(frm);
		}, group);
	},
});

function import_estimates(frm) {
	let ready = false;
	const dialog = new frappe.ui.Dialog({
		title: __("Import estimates"),
		size: "large",
		fields: [
			{ fieldtype: "HTML", fieldname: "help", options: `<p class="text-muted">${__(
				"One .xlsx or .csv for the whole BOQ: each row is one resource of a line, named by <b>boq_ref</b>. Columns: <b>resource_type</b> (Material, Labour, Equipment, Subcontract, Other), <b>item_code</b> or <b>description</b>, <b>uom</b>, <b>qty_per_unit</b> and <b>wastage_percent</b> (materials), <b>output_per_day</b> (labour and equipment: BOQ units a day), <b>rate</b> (leave it blank on an item to fetch the price). A line with no rows is left alone; a line with rows gets them in place of what its sheet had. If any row fails, nothing is imported."
			)}</p><p>${__("<b>Download template</b> (below) lists every line of this BOQ, ready to fill.")}</p>` },
			{ fieldtype: "Attach", fieldname: "file", label: __("Resources (xlsx or csv)"), reqd: 1,
			  options: { restrictions: { allowed_file_types: [".xlsx", ".csv"] } },
			  onchange: () => check(dialog.get_value("file")) },
			{ fieldtype: "HTML", fieldname: "result" },
		],
		primary_action_label: __("Import"),
		primary_action() {
			if (!ready) return frappe.msgprint(__("Upload a file that passes the checks first."));
			frappe.xcall(`${BOQ_EST}.import_estimates`, { boq: frm.doc.name, file_url: dialog.get_value("file") }).then((r) => {
				dialog.hide();
				frm.reload_doc();
				frappe.msgprint({ title: __("{0} estimate sheets filled", [r.sheets.length]), indicator: "green",
					message: `<table class="table table-sm"><thead><tr><th>${__("Line")}</th><th>${__("Sheet")}</th><th class="text-right">${__("Resources")}</th><th class="text-right">${__("Unit cost")}</th></tr></thead><tbody>${r.sheets
						.map((s) => `<tr><td>${frappe.utils.escape_html(s.boq_ref)}</td><td><a href="/app/estimate-sheet/${s.sheet}">${s.sheet}</a></td><td class="text-right">${s.resources}</td><td class="text-right">${format_currency(s.unit_cost, frm.doc.currency)}</td></tr>`)
						.join("")}</tbody></table>` });
			});
		},
	});
	dialog.set_secondary_action_label(__("Download template"));
	dialog.set_secondary_action(() => window.open(`/api/method/${BOQ_EST}.download_template?boq=${encodeURIComponent(frm.doc.name)}`));
	dialog.get_primary_btn().prop("disabled", true);
	function check(file_url) {
		ready = false;
		dialog.get_primary_btn().prop("disabled", true);
		const area = dialog.fields_dict.result.$wrapper;
		if (!file_url) return area.empty();
		area.html(`<p class="text-muted">${__("Checking...")}</p>`);
		frappe.xcall(`${BOQ_EST}.read_resources`, { file_url, boq: frm.doc.name }).then((r) => {
			area.html(a3_constructa.resources_summary(r, frm.doc.currency));
			ready = !r.errors.length;
			dialog.get_primary_btn().prop("disabled", !ready);
		});
	}
	dialog.show();
}
