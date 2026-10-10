// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// A sheet exists once its line is opened; this creates them for every line of a BOQ.
frappe.listview_settings["Estimate Sheet"] = {
	onload(list) {
		list.page.add_inner_button(__("Sheets for a BOQ's lines"), () => {
			const filter = (list.filter_area.get() || []).find((f) => f[1] === "boq" && f[2] === "=");
			frappe.prompt(
				[{ fieldname: "boq", fieldtype: "Link", options: "BOQ", label: __("BOQ"), reqd: 1, default: filter && filter[3],
				   get_query: () => ({ filters: { docstatus: 0 } }) }],
				({ boq }) => frappe.xcall("a3_constructa.api.estimate_import.make_sheets", { boq }).then((r) => {
					frappe.show_alert({ message: r.made.length
						? __("{0} estimate sheets created for {1}.", [r.made.length, boq])
						: __("Every line of {0} already has its sheet.", [boq]), indicator: "green" });
					list.filter_area.clear(false).then(() => list.filter_area.add([["Estimate Sheet", "boq", "=", boq]]));
				}),
				__("An estimate sheet for every line"), __("Create"));
		});
	},
};
