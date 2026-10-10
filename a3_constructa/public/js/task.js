// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 6.1-6.3: a task on the WBS, its BOQ line and the resources it needs.
const TR = "a3_constructa.overrides.task_resources";

frappe.ui.form.on("Task", {
	setup(frm) {
		const by_project = () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} });
		frm.set_query("wbs", by_project);
		frm.set_query("crew", () => ({ filters: { is_active: 1 } }));
		frm.set_query("boq", () => ({ filters: { docstatus: ["<", 2], ...(frm.doc.project ? { project: frm.doc.project } : {}) } }));
		frm.set_query("crew", "resources", () => ({ filters: { is_active: 1 } }));
		frm.set_query("cost_code", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		if (frm.is_new() || frm.doc.is_template) return;
		if (!frm.doc.is_group && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Record progress"), () => record_progress(frm));
		}
		if (!frm.doc.is_group && !frm.doc.is_milestone && frm.doc.status !== "Cancelled") {
			frm.add_custom_button(__("Request inspection"), () => request_inspection(frm), __("Quality"));
			frm.add_custom_button(__("Inspections"), () => frappe.set_route("List", "Quality Inspection", { task: frm.doc.name }), __("Quality"));
			frm.add_custom_button(__("NCRs"), () => frappe.set_route("List", "Non Conformance", { task: frm.doc.name }), __("Quality"));
		}
		if (frm.doc.boq) {
			frm.add_custom_button(__("Pick BOQ line"), () => pick_line(frm), __("Resources"));
		}
		if (frm.doc.boq_item) {
			frm.add_custom_button(__("Fill from estimate"), () =>
				frappe.xcall(`${TR}.fill_from_estimate`, { task: frm.doc.name }).then((r) => {
					const notes = [__("{0} rows from {1}", [r.rows, r.estimate_sheet])];
					if (r.skipped.length) notes.push(__("Left out (not on-site labour, plant or material): {0}", [r.skipped.join(", ")]));
					if (r.too_long.length) notes.push(__("Longer than the task: {0}", [r.too_long.join("; ")]));
					frappe.msgprint(notes.join("<br>"), __("Fill from estimate"));
					frm.reload_doc();
				})
			, __("Resources"));
		}
	},
});

// Catalogue 6.8: a draft inspection with the task type's checklist.
function request_inspection(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Request inspection of {0}", [frm.doc.subject]),
		fields: [
			{ fieldname: "inspection_point", label: __("Inspection Point"), fieldtype: "Select", options: "Hold\nWitness\nSurveillance", default: "Hold", reqd: 1,
			  description: __("Hold: work stops until accepted. Witness: the client's engineer is invited. Surveillance: checked as the work goes.") },
			{ fieldname: "report_date", label: __("Inspection Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
			{ fieldname: "inspected_by", label: __("Inspected By"), fieldtype: "Link", options: "User", default: frappe.session.user, reqd: 1 },
		],
		primary_action_label: __("Request"),
		primary_action(values) {
			frappe.xcall("a3_constructa.overrides.quality.request_inspection", { task: frm.doc.name, ...values }).then((name) => {
				d.hide();
				frappe.set_route("Form", "Quality Inspection", name);
			});
		},
	});
	d.show();
}

function pick_line(frm) {
	frappe.xcall(`${TR}.boq_lines`, { boq: frm.doc.boq }).then((lines) => {
		const label = (l) => [l.boq_ref, (l.description || l.item_name || "").slice(0, 90), `${l.boq_qty} ${l.uom || ""}`].filter(Boolean).join(" · ");
		const d = new frappe.ui.Dialog({
			title: __("BOQ line of {0}", [frm.doc.subject]),
			fields: [{ fieldtype: "Select", fieldname: "line", label: __("Line"), reqd: 1, default: frm.doc.boq_item,
			           options: lines.map((l) => ({ value: l.name, label: label(l) })) }],
			primary_action_label: __("Use this line"),
			primary_action({ line }) {
				const l = lines.find((x) => x.name === line);
				frm.set_value("boq_item", line);
				if (!flt(frm.doc.planned_qty) && l) frm.set_value({ planned_qty: l.boq_qty, uom: l.uom });
				d.hide();
				frm.save();
			},
		});
		d.show();
	});
}

frappe.ui.form.on("Task Resource", {
	qty_per_day: (frm, cdt, cdn) => total(cdt, cdn),
	days: (frm, cdt, cdn) => total(cdt, cdn),
});

function total(cdt, cdn) {
	const r = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "total_qty", flt(r.qty_per_day) * cint(r.days));
}

function record_progress(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Record progress on {0}", [frm.doc.subject]),
		fields: [
			{ fieldtype: "Date", fieldname: "date", label: __("Date"), reqd: 1, default: frappe.datetime.get_today() },
			{ fieldtype: "Float", fieldname: "qty_done", label: __("Quantity done ({0})", [frm.doc.uom || ""]), reqd: 1,
			  description: __("Done on this date. Planned {0}, done so far {1}.", [frm.doc.planned_qty || 0, frm.doc.qty_done || 0]) },
			{ fieldtype: "Data", fieldname: "reference", label: __("Reference") },
			{ fieldtype: "Data", fieldname: "remarks", label: __("Remarks") },
		],
		primary_action_label: __("Record"),
		primary_action(values) {
			frappe.xcall("a3_constructa.overrides.task_progress.record_progress", { task: frm.doc.name, ...values }).then((p) => {
				d.hide();
				frappe.show_alert({ message: __("{0}% complete", [p]), indicator: "green" });
				frm.reload_doc();
			});
		},
	});
	d.show();
}
