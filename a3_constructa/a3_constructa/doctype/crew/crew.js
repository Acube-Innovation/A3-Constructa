// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 7.1: a member's daily rate comes from their salary structure; the
// crew's cost follows its active members.
frappe.ui.form.on("Crew", {
	setup(frm) {
		const active = () => ({ filters: { status: "Active", ...(frm.doc.company ? { company: frm.doc.company } : {}) } });
		frm.set_query("foreman", active);
		frm.set_query("employee", "members", active);
		frm.set_query("project", () => ({ filters: frm.doc.company ? { company: frm.doc.company } : {} }));
	},
	standard_output: (frm) => calculate(frm),
});

frappe.ui.form.on("Crew Member", {
	employee(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.employee) return;
		frappe.xcall("a3_constructa.a3_constructa.doctype.crew.crew.daily_wage", { employee: row.employee }).then((rate) => {
			if (rate) frappe.model.set_value(cdt, cdn, "daily_rate", rate);
		});
	},
	daily_rate: (frm) => calculate(frm),
	is_active: (frm) => calculate(frm),
	members_remove: (frm) => calculate(frm),
});

function calculate(frm) {
	const active = (frm.doc.members || []).filter((m) => m.is_active);
	const cost = active.reduce((sum, m) => sum + flt(m.daily_rate), 0);
	frm.set_value("headcount", active.length);
	frm.set_value("daily_cost", cost);
	frm.set_value("unit_labour_cost", flt(frm.doc.standard_output) ? cost / flt(frm.doc.standard_output) : 0);
}
