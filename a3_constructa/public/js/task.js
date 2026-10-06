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

function pick_line(frm) {
	frappe.xcall(`${TR}.boq_lines`, { boq: frm.doc.boq }).then((lines) => {
		const label = (l) => [l.boq_ref, (l.description || l.item_name || "").slice(0, 90), `${l.boq_qty} ${l.uom || ""}`].filter(Boolean).join(" · ");
		const d = new frappe.ui.Dialog({
			title: __("BOQ line of {0}", [frm.doc.subject]),
			fields: [{ fieldtype: "Select", fieldname: "line", label: __("Line"), reqd: 1, options: lines.map((l) => ({ value: l.name, label: label(l) })) }],
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
