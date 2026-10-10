// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 5.4: the plan follows the schedule.
frappe.ui.form.on("Procurement Plan", {
	setup(frm) {
		frm.set_query("task", "items", () => ({ filters: { project: frm.doc.project, is_group: 0 } }));
		frm.set_query("wbs", "items", () => ({ filters: { project: frm.doc.project } }));
	},
	refresh(frm) {
		if (frm.is_new() || ["Cancelled", "Completed"].includes(frm.doc.status)) return;
		frm.add_custom_button(__("Refresh from schedule"), () =>
			frm.call("refresh_from_schedule").then(({ message: r }) => {
				const lines = [__("{0} added, {1} updated, {2} removed; {3} lines now.", [r.added, r.updated, r.removed, r.lines])];
				if (r.kept.length) lines.push(__("Kept, already requested though no longer on a task: {0}", [r.kept.join(", ")]));
				frappe.show_alert({ message: lines.join("<br>"), indicator: "green" }, 7);
				frm.reload_doc();
			})
		);
		const overdue = (frm.doc.items || []).filter((r) => r.pr_overdue).length;
		if (overdue) {
			frm.dashboard.set_headline_alert(
				`<span class="indicator red">${overdue === 1 ? __("1 line past its PR date with nothing requested")
				: __("{0} lines past their PR date with nothing requested", [overdue])}</span>`);
		}
		frm.add_custom_button(__("Material Request"), () => {
			const picked = frm.fields_dict.items.grid.get_selected_children().map((r) => r.name);
			frm.call("make_material_request", { rows: picked.length ? picked : null })
				.then(({ message }) => frappe.set_route("Form", "Material Request", message));
		}, __("Create"));
	},
});
