// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// Award Procurement: one awarded project's buying, from its BOQ to what arrived.
//
// This page is only a frame. The view is the "Award Procurement View" Custom
// HTML Block, drawn with the same shared code as the workspace overviews
// (custom_html_block/award_procurement_view/). The route carries the award,
// /app/award-procurement/AQ-2026-0001; without one the view lists the awards.

frappe.pages["award-procurement"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Award Procurement"),
		single_column: true,
	});

	wrapper.award_field = page.add_field({
		fieldname: "awarded_quotation",
		label: __("Awarded Quotation"),
		fieldtype: "Link",
		options: "Awarded Quotation",
		change() {
			// Only a different award navigates. Filling the field from the route
			// also fires this, briefly with no value, and must not leave the page.
			const award = this.get_value();
			if (award && award !== wrapper.shown_award) frappe.set_route("award-procurement", award);
		},
	});

	page.add_inner_button(__("All awards"), () => frappe.set_route("award-procurement"));

	page.set_secondary_action(__("Line-by-line report"), () => {
		const award = frappe.get_route()[1];
		frappe.set_route("query-report", "Award Procurement Status", award ? { awarded_quotation: award } : {});
	});

	wrapper.view = $('<div class="award-procurement-view"></div>').appendTo(page.main);
};

frappe.pages["award-procurement"].on_page_show = function (wrapper) {
	const award = frappe.get_route()[1] || null;
	if (wrapper.shown_award === award) return;
	wrapper.shown_award = award;
	wrapper.award_field.set_value(award || "");

	// The block reads the award from the route when it runs.
	frappe.model.with_doc("Custom HTML Block", "Award Procurement View").then((block) => {
		wrapper.view.empty();
		frappe.create_shadow_element(wrapper.view[0], block.html, block.style, block.script);
	});
};
