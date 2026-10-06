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
		frappe.db.get_value("Asset", frm.doc.asset, ["project", "location", "current_meter", "wbs", "cost_code"]).then(({ message: a }) => {
			if (!a) return;
			if (!frm.doc.project && a.project) frm.set_value("project", a.project);
			if (!frm.doc.site && a.location) frm.set_value("site", a.location);
			if (!frm.doc.wbs && a.wbs) frm.set_value("wbs", a.wbs);
			if (!frm.doc.cost_code && a.cost_code) frm.set_value("cost_code", a.cost_code);
			if (!flt(frm.doc.meter_start)) frm.set_value("meter_start", a.current_meter);
		});
	},
	worked_hours: (frm) => amount(frm),
	internal_rate: (frm) => amount(frm),
});

function amount(frm) {
	frm.set_value("amount", frm.doc.is_hired ? 0 : flt(frm.doc.worked_hours) * flt(frm.doc.internal_rate));
}
