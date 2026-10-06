// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 9.3: approval levels from the Approval Matrix on Material Request
// and Purchase Order. Shows where the document stands and, to the person who
// gives the next level, Approve and Reject buttons.
["Material Request", "Purchase Order"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			show_approval_state(frm);
		},
	});
});

function show_approval_state(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 0) return;
	frappe
		.xcall("a3_constructa.overrides.approvals.get_status", { doctype: frm.doctype, name: frm.doc.name })
		.then((s) => {
			if (!s.required) return;
			const done = __("{0} of {1} approval levels done", [s.reached, s.required]);
			if (s.rejected) {
				frm.set_intro(__("Rejected. Correct it and save; every level then approves again."), "red");
			} else if (s.next_level) {
				frm.set_intro(__("Waiting for level {0} approval: {1}. {2}.", [s.next_level, s.next_approver, done]), "orange");
			} else {
				frm.set_intro(__("All {0} approval levels done. It can be submitted.", [s.required]), "green");
			}
			if (!s.can_act) return;
			const group = __("Approval");
			frm.add_custom_button(__("Approve level {0}", [s.next_level]), () => act(frm, "approve", s), group);
			frm.add_custom_button(__("Reject"), () => act(frm, "reject", s), group);
			frm.page.set_inner_btn_group_as_primary(group);
		});
}

function act(frm, action, s) {
	const reject = action === "reject";
	frappe.prompt(
		[{
			fieldname: "comment",
			fieldtype: "Small Text",
			label: reject ? __("Why is it rejected?") : __("Comment (optional)"),
			reqd: reject ? 1 : 0,
		}],
		(values) => {
			frappe
				.xcall(`a3_constructa.overrides.approvals.${action}`, {
					doctype: frm.doctype,
					name: frm.doc.name,
					comment: values.comment,
				})
				.then(() => {
					frappe.show_alert({
						message: reject ? __("Rejected") : __("Level {0} approved", [s.next_level]),
						indicator: reject ? "red" : "green",
					});
					frm.reload_doc();
				});
		},
		reject ? __("Reject {0}", [frm.doc.name]) : __("Approve level {0}", [s.next_level]),
		reject ? __("Reject") : __("Approve")
	);
}
