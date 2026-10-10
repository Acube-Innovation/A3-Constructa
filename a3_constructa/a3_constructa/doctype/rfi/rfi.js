// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("RFI", {
	refresh(frm) {
		if (frm.is_new()) return;
		const overdue = frm.doc.status === "Open" && moment(frm.doc.required_by).isBefore(moment(), "day");
		if (overdue) {
			frm.set_intro(__("Overdue: the answer was needed by {0}.", [frappe.datetime.str_to_user(frm.doc.required_by)]), "red");
		}
		if ((frm.doc.cost_impact || frm.doc.time_impact) && !frm.doc.change_event && frm.doc.status !== "Open") {
			frm.add_custom_button(__("Raise change event"), () =>
				frappe
					.xcall("a3_constructa.a3_constructa.doctype.rfi.rfi.raise_change_event", { rfi: frm.doc.name })
					.then((name) => {
						frm.reload_doc();
						frappe.show_alert({ message: __("Change event {0} raised", [name]), indicator: "green" });
					})
			);
			frm.dashboard.set_headline(__("The answer has a cost or time impact: raise its change event."), "orange");
		}
	},
	cost_impact: (frm) => frm.dirty() && frm.refresh(),
	time_impact: (frm) => frm.dirty() && frm.refresh(),
});
