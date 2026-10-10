// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 8.1 / 8.3: a machine's day, charged to the job at its internal rate.
frappe.ui.form.on("Equipment Log", {
	setup(frm) {
		frm.set_query("asset", () => ({ filters: { docstatus: ["<", 2] } }));
		frm.set_query("cost_code", () => ({ filters: { category: "Equipment" } }));
		frm.set_query("wbs", () => ({ filters: frm.doc.project ? { project: frm.doc.project } : {} }));
		frm.set_query("operator", () => ({ filters: { status: "Active" } }));
	},
	refresh(frm) {
		frm.set_intro();
		if (frm.doc.is_hired) {
			frm.set_intro(__("Hired plant: the hours are logged, the cost comes through the hire order and the supplier's invoice."), "blue");
		}
	},
	asset(frm) {
		if (!frm.doc.asset) return;
		frappe.xcall("a3_constructa.a3_constructa.doctype.equipment_log.equipment_log.asset_defaults", { asset: frm.doc.asset }).then((a) => {
			if (!a) return;
			frm.set_value({ asset_name: a.asset_name, company: a.company, is_hired: a.is_hired, meter_type: a.meter_type || "Hours",
			                internal_rate: a.is_hired ? 0 : a.internal_hourly_rate });
			if (!frm.doc.project && a.project) frm.set_value("project", a.project);
			if (!frm.doc.site && a.location) frm.set_value("site", a.location);
			if (!frm.doc.wbs && a.wbs) frm.set_value("wbs", a.wbs);
			if (!frm.doc.cost_code && a.cost_code) frm.set_value("cost_code", a.cost_code);
			if (!flt(frm.doc.meter_start)) frm.set_value("meter_start", a.meter_start);
			amount(frm);
			frm.refresh();
		});
	},
	worked_hours: (frm) => amount(frm),
	internal_rate: (frm) => amount(frm),
});

function amount(frm) {
	frm.set_value("amount", frm.doc.is_hired ? 0 : flt(frm.doc.worked_hours) * flt(frm.doc.internal_rate));
}
