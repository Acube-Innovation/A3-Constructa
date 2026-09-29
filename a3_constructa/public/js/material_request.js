// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Material Request: Get Items From > BOQ.
//
// Pulls approved BOQ lines into this request so the packages of an award, or of
// several awards, are bought together. Each line keeps its project, cost head,
// WBS and cost code, and remembers the BOQ line it buys (boq, boq_item) so the
// procurement reports can follow it to the order and the receipt. The server
// checks that link again on save (a3_constructa/overrides/material_request.py).

frappe.ui.form.on("Material Request", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("BOQ"), () => open_boq_dialog(frm), __("Get Items From"));

		// Arriving from an award's Create > Material Request.
		const award = frappe.flags.a3_request_from_award;
		if (award && frm.is_new()) {
			frappe.flags.a3_request_from_award = null;
			open_boq_dialog(frm, { awarded_quotation: award });
		}
	},
});

function open_boq_dialog(frm, preset = {}) {
	let lines = [];
	let loaded_for = null;

	const dialog = new frappe.ui.Dialog({
		title: __("Get Items From BOQ"),
		size: "extra-large",
		fields: [
			{
				fieldname: "awarded_quotation",
				fieldtype: "Link",
				options: "Awarded Quotation",
				label: __("Awarded Quotation"),
				default: preset.awarded_quotation,
				get_query: () => ({ filters: { status: ["not in", ["Draft", "Cancelled"]] } }),
				change: () => load(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "project",
				fieldtype: "Link",
				options: "Project",
				label: __("Project"),
				get_query: () => ({ filters: { company: frm.doc.company } }),
				change: () => load(),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "schedule_date",
				fieldtype: "Date",
				label: __("Required By"),
				reqd: 1,
				default: frm.doc.schedule_date || frappe.datetime.add_days(frappe.datetime.get_today(), 14),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "warehouse",
				fieldtype: "Link",
				options: "Warehouse",
				label: __("For Warehouse"),
				default: frm.doc.set_warehouse,
				get_query: () => ({ filters: { company: frm.doc.company, is_group: 0 } }),
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "lines_html", fieldtype: "HTML" },
		],
		primary_action_label: __("Add to Material Request"),
		primary_action: (values) => add_lines(values),
	});

	const $area = dialog.fields_dict.lines_html.$wrapper;
	$area.html(`<p class="text-muted">${__("Choose an awarded quotation or a project to list its approved BOQ lines.")}</p>`);
	dialog.show();
	if (preset.awarded_quotation) load();

	function load() {
		const { awarded_quotation, project } = dialog.get_values(true);
		const key = `${awarded_quotation || ""}|${project || ""}`;
		if (key === loaded_for) return;
		loaded_for = key;
		if (!awarded_quotation && !project) {
			lines = [];
			render();
			return;
		}
		$area.html(`<p class="text-muted">${__("Loading BOQ lines…")}</p>`);
		frappe
			.xcall("a3_constructa.api.boq_procurement.get_request_lines", {
				awarded_quotation,
				project,
				company: frm.doc.company,
			})
			.then((result) => {
				lines = result.map((line) => ({ ...line, selected: line.to_request > 0, qty: line.to_request }));
				render();
			});
	}

	function render() {
		$area.empty();
		if (!lines.length) {
			$area.append(
				$("<p class='text-muted'>").text(
					loaded_for && loaded_for !== "|"
						? __("No approved BOQ lines here. A BOQ can be requested from once it is approved.")
						: __("Choose an awarded quotation or a project to list its approved BOQ lines.")
				)
			);
			return;
		}

		const $summary = $("<div class='boq-dialog-summary text-muted small' style='margin-bottom: var(--margin-sm)'>");
		const $table = $(`<table class="table table-bordered" style="font-size: var(--text-sm)">
			<thead><tr>
				<th style="width: 32px"><input type="checkbox" class="boq-select-all"></th>
				<th>${__("Item")}</th><th>${__("WBS")}</th><th>${__("Cost Code")}</th>
				<th class="text-right">${__("Approved")}</th><th class="text-right">${__("Requested")}</th>
				<th class="text-right">${__("To Request")}</th><th style="width: 130px">${__("Qty")}</th>
			</tr></thead><tbody></tbody></table>`);
		const $body = $table.find("tbody");

		let group = null;
		for (const line of lines) {
			if (line.boq !== group) {
				group = line.boq;
				const heading = [line.component, line.boq, line.project_name].filter(Boolean).join(" · ");
				$body.append($("<tr>").append($("<td colspan='8' class='text-muted bold'>").text(heading)));
			}
			const done = line.to_request <= 0;
			const $row = $("<tr>").toggleClass("text-muted", done);
			const $check = $("<input type='checkbox'>").prop("checked", line.selected);
			const $qty = $("<input type='number' min='0' step='any' class='form-control input-xs'>").val(line.qty);
			$check.on("change", () => {
				line.selected = $check.prop("checked");
				summarise();
			});
			$qty.on("input", () => {
				line.qty = flt($qty.val());
				line.selected = line.qty > 0;
				$check.prop("checked", line.selected);
				summarise();
			});
			const requested = line.requested_qty + line.draft_qty;
			$row.append(
				$("<td>").append($check),
				$("<td>").append(
					$("<div>").text(line.item_code),
					$("<div class='text-muted small'>").text(line.item_name || "")
				),
				$("<td>").text(line.wbs || ""),
				$("<td>").text(line.cost_code || ""),
				$("<td class='text-right'>").text(`${qty_text(line.approved_qty)} ${line.uom || ""}`),
				$("<td class='text-right'>").text(qty_text(requested)),
				$("<td class='text-right'>").text(done ? __("Fully requested") : qty_text(line.to_request)),
				$("<td>").append($qty)
			);
			$body.append($row);
		}

		$table.find(".boq-select-all").on("change", function () {
			// Lines with nothing left to request stay unticked.
			const on = $(this).prop("checked");
			for (const line of lines) line.selected = on && line.qty > 0;
			$body.find("input[type=checkbox]").each(function (index) {
				$(this).prop("checked", lines[index].selected);
			});
			summarise();
		});

		$area.append($summary, $("<div style='max-height: 55vh; overflow: auto'>").append($table));
		summarise();

		function summarise() {
			const chosen = lines.filter((line) => line.selected && line.qty > 0);
			// The same item across several packages is what gets bought together.
			const together = {};
			for (const line of chosen) {
				const key = `${line.item_code}|${line.uom}`;
				together[key] = together[key] || { item: line.item_code, uom: line.uom, qty: 0, lines: 0 };
				together[key].qty += line.qty;
				together[key].lines += 1;
			}
			const shared = Object.values(together).filter((entry) => entry.lines > 1);
			let text = __("{0} of {1} lines selected.", [chosen.length, lines.length]);
			if (shared.length) {
				text +=
					" " +
					__("Bought together: {0}", [
						shared.map((e) => `${e.item} ${qty_text(e.qty)} ${e.uom || ""} (${e.lines})`).join(", "),
					]);
			}
			$summary.text(text);
		}
	}

	function add_lines(values) {
		const chosen = lines.filter((line) => line.selected && line.qty > 0);
		if (!chosen.length) {
			frappe.msgprint(__("Choose at least one line with a quantity."));
			return;
		}

		// A new request starts with one empty row; replace it rather than keep it.
		if ((frm.doc.items || []).every((row) => !row.item_code)) frm.clear_table("items");
		if (!frm.doc.schedule_date) frm.set_value("schedule_date", values.schedule_date);
		if (!frm.doc.set_warehouse && values.warehouse) frm.set_value("set_warehouse", values.warehouse);

		for (const line of chosen) {
			const row = {
				item_code: line.item_code,
				item_name: line.item_name,
				description: line.description || line.item_name,
				item_group: line.item_group,
				uom: line.uom,
				stock_uom: line.stock_uom,
				conversion_factor: line.conversion_factor,
				qty: line.qty,
				stock_qty: line.qty * line.conversion_factor,
				rate: line.rate,
				amount: line.qty * line.rate,
				schedule_date: values.schedule_date,
				warehouse: values.warehouse,
				project: line.project,
				cost_head: line.cost_head,
				wbs: line.wbs,
				cost_code: line.cost_code,
				boq: line.boq,
				boq_item: line.boq_item,
			};
			// Fetching the same BOQ line (and WBS part of it) twice updates it
			// instead of adding a duplicate.
			const existing = (frm.doc.items || []).find(
				(item) => item.boq_item === line.boq_item && (item.wbs || "") === (line.wbs || "")
			);
			if (existing) Object.assign(existing, row);
			else frm.add_child("items", row);
		}

		frm.refresh_field("items");
		frm.dirty();
		dialog.hide();
		frappe.show_alert({ message: __("{0} lines added from the BOQ", [chosen.length]), indicator: "green" });
	}
}

// Whole quantities without decimals; fractional ones (2.5 t) keep up to three.
function qty_text(value) {
	return format_number(value, null, Number.isInteger(flt(value, 3)) ? 0 : 3);
}
