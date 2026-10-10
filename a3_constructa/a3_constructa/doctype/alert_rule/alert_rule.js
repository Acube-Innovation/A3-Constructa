// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Catalogue 13.6: see what the rule would send now, or send it.
frappe.ui.form.on("Alert Rule", {
	refresh(frm) {
		frm.set_intro(
			__("Runs every morning ({0}). It looks at the same records as the overview tabs' Needs attention list; an item already alerted is not sent again for 7 days.",
				[frm.doc.frequency === "Weekly" ? __("once a week") : __("daily")]),
			"blue"
		);
		if (frm.is_new()) return;
		frm.add_custom_button(__("Preview"), () =>
			frappe.xcall("a3_constructa.api.alerts.run_now", { rule: frm.doc.name, send: 0 }).then((r) => show(r, __("Would send now"))));
		if (frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Run now"), () =>
				frappe.xcall("a3_constructa.api.alerts.run_now", { rule: frm.doc.name, send: 1 }).then((r) => {
					frm.reload_doc();
					show(r, __("Sent"));
				}));
		}
	},
	condition(frm) {
		frm.set_value("threshold_unit", frm.doc.condition === "WBS over budget" ? "%" : "days");
	},
});

function show(r, title) {
	const items = r.items.length
		? `<ul>${r.items.map((i) => `<li><a href="/app/${frappe.router.slug(i.doctype)}/${encodeURIComponent(i.name)}">${frappe.utils.escape_html(i.name)}</a>: ${frappe.utils.escape_html(i.detail)}</li>`).join("")}</ul>`
		: `<p class="text-muted">${__("Nothing new to send.")}</p>`;
	frappe.msgprint({
		title: `${title}: ${r.new}`,
		indicator: r.new ? "orange" : "green",
		message: `<p>${__("{0} found; {1} new; {2} already sent in the last 7 days. Recipients: {3}.", [r.found, r.new, r.held, r.users.length ? r.users.join(", ") : __("none")])}</p>${items}`,
	});
}
