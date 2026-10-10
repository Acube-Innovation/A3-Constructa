// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

const DSR = "a3_constructa.a3_constructa.doctype.daily_site_report.daily_site_report";

frappe.ui.form.on("Daily Site Report", {
	setup(frm) {
		const on_project = () => ({ filters: { project: frm.doc.project, is_group: 0, status: ["not in", ["Completed", "Cancelled", "Template"]] } });
		for (const table of ["labour", "equipment", "progress"]) frm.set_query("task", table, on_project);
		for (const table of ["labour", "equipment", "materials"]) frm.set_query("wbs", table, () => ({ filters: { project: frm.doc.project } }));
		frm.set_query("crew", "labour", () => ({ filters: { is_active: 1 } }));
		frm.set_query("cost_code", "equipment", () => ({ filters: { category: "Equipment", status: "Active" } }));
		frm.set_query("warehouse", "materials", () => ({ filters: { company: frm.doc.company, is_group: 0 } }));
	},
	project(frm) {
		if (!frm.doc.project) return;
		frappe.call({ method: `${DSR}.defaults`, args: { project: frm.doc.project } }).then(({ message: d }) => {
			frm.__store = d.store;
			if (d.site && !frm.doc.site) frm.set_value("site", d.site);
		});
	},
	refresh(frm) {
		if (frm.doc.project && frm.__store === undefined) frm.trigger("project");
	},
});

frappe.ui.form.on("DSR Material", {
	materials_add(frm, cdt, cdn) {
		if (frm.__store) frappe.model.set_value(cdt, cdn, "warehouse", frm.__store);
	},
});
