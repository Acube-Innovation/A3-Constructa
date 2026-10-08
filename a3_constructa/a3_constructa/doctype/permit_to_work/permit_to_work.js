// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Permit to Work", {
	permit_type(frm) {
		if ((frm.doc.precautions || []).some((p) => p.confirmed)) return;
		frappe
			.xcall("a3_constructa.hse.standard_precautions", { permit_type: frm.doc.permit_type })
			.then((list) => {
				frm.clear_table("precautions");
				list.forEach((precaution) => frm.add_child("precautions", { precaution }));
				frm.refresh_field("precautions");
			});
	},

	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Open") {
			if (frm.doc.status !== "Open" && !frm.is_new()) {
				frm.set_intro(
					__("{0} by {1} on {2}.", [
						__(frm.doc.status),
						frappe.user.full_name(frm.doc.closed_by),
						frappe.datetime.str_to_user(frm.doc.closed_on),
					]),
					frm.doc.status === "Closed" ? "green" : "gray"
				);
			}
			return;
		}
		const expired = moment(frm.doc.valid_to).isBefore(moment());
		frm.set_intro(
			expired
				? __("Expired {0}: work must stop until it is closed and a new permit issued.", [frappe.datetime.prettyDate(frm.doc.valid_to)])
				: __("Open until {0}.", [frappe.datetime.str_to_user(frm.doc.valid_to)]),
			expired ? "red" : "blue"
		);
		frm.add_custom_button(__("Close permit"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Sign off the permit"),
				fields: [{ fieldname: "note", fieldtype: "Small Text", label: __("How was the area left?"), reqd: 1 }],
				primary_action_label: __("Close permit"),
				primary_action({ note }) {
					frappe
						.xcall("a3_constructa.a3_constructa.doctype.permit_to_work.permit_to_work.sign_off", {
							name: frm.doc.name,
							status: "Closed",
							note,
						})
						.then(() => {
							d.hide();
							frm.reload_doc();
						});
				},
			});
			d.show();
		});
		frm.add_custom_button(__("Cancel permit"), () =>
			frappe.confirm(__("Cancel this permit? Work under it must not start."), () =>
				frappe
					.xcall("a3_constructa.a3_constructa.doctype.permit_to_work.permit_to_work.sign_off", {
						name: frm.doc.name,
						status: "Cancelled",
					})
					.then(() => frm.reload_doc())
			)
		);
	},
});
