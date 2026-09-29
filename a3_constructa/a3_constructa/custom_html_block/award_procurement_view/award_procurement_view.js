// Award Procurement View: the body of the Award Procurement page
// (a3_constructa/a3_constructa/page/award_procurement/).
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Award Procurement View" Custom HTML Block on every `bench migrate`
// (a3_constructa/setup/custom_html_blocks.py). Edit them here, not in the desk.

function render(data) {
	if (data.restricted) {
		return [
			el(
				"div",
				{ class: "ov-card" },
				el("p", {
					class: "ov-empty",
					text: __(
						"Procurement progress needs read access to BOQs, Material Requests, Purchase Orders and Purchase Receipts."
					),
				})
			),
		];
	}
	if (!data.award) {
		return [
			section({
				title: __("Choose an award"),
				caption: __("Active awards and how much of each approved BOQ has been bought. Open one for its detail."),
				body: render_award_rows(data.awards, data.currency, __("No active awards yet.")),
			}),
		];
	}

	const { award, currency } = data;
	return [
		render_heading(award, currency),
		render_summary(data),
		section({
			title: __("By package"),
			caption: __("Each package's approved BOQ, weighted by budget, with the client BOQ lines it prices"),
			body: render_components(data.components, currency),
		}),
		section({
			title: __("Still to buy"),
			caption: __("The BOQ lines with the most budget still to arrive"),
			body: render_pending(data.pending, currency),
			action: report_link(
				"Award Procurement Status",
				{ awarded_quotation: award.name },
				__("Line-by-line report"),
				{ class: "ov-button" }
			),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Late purchase orders"),
				caption: __("Open orders past their delivery date"),
				body: render_late_orders(data.late_orders, currency),
			}),
			section({
				title: __("Shipments on the way"),
				caption: __("Tracked shipments for this award's orders or project"),
				body: render_shipments(data.shipments),
			})
		),
		section({
			title: __("Documents"),
			caption: __("{0} requests · {1} purchase orders · {2} receipts, newest first", [
				data.document_counts.requests,
				data.document_counts.orders,
				data.document_counts.receipts,
			]),
			body: el(
				"div",
				{ class: "ov-docs" },
				render_documents(__("Material requests"), "Material Request", data.requests, (doc) => [
					doc.name,
					`${format_date(doc.transaction_date)} · ${__(doc.status)} · ${__("{0}% ordered", [Math.round(doc.per_ordered || 0)])}`,
					null,
				]),
				render_documents(__("Purchase orders"), "Purchase Order", data.orders, (doc) => [
					doc.supplier,
					`${doc.name} · ${__(doc.status)}`,
					format_money(doc.base_net_total, currency),
				]),
				render_documents(__("Purchase receipts"), "Purchase Receipt", data.receipts, (doc) => [
					doc.supplier,
					`${doc.name} · ${format_date(doc.posting_date)}`,
					format_money(doc.base_net_total, currency),
				])
			),
		}),
	];
}

function render_heading(award, currency) {
	const meta = [award.customer, award.project_name || award.project, __(award.status)].filter(Boolean).join(" · ");
	return el(
		"div",
		{ class: "ov-heading" },
		form_link("Awarded Quotation", award.name, el("h2", { class: "ov-heading-title", text: award.title })),
		el("p", { class: "ov-heading-meta", text: `${award.name} · ${meta}` })
	);
}

function render_summary(data) {
	const { award, currency, off_boq, late_orders, shipments } = data;
	const hero = el(
		"div",
		{ class: "ov-card ov-hero" },
		el("p", { class: "ov-label", text: __("On order") }),
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: `${Math.round(award.ordered)}%` }),
			el("span", { class: "ov-hero-of", text: __("of the approved BOQ, by budget") })
		),
		award.lines
			? el("div", { class: "ov-hero-stages" }, render_stages(award, award.title), stage_figures(award, { labelled: true }))
			: el("p", { class: "ov-hero-caption", text: __("This award has no approved BOQ yet, so there is nothing to trace.") })
	);

	const late = late_orders.length;
	return el(
		"div",
		{ class: "ov-summary" },
		hero,
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("BOQ budget"),
				format_money(award.budget, currency),
				note(__("{0} lines in {1} approved BOQs", [award.lines, award.boqs]))
			),
			kpi(
				__("Committed on purchase orders"),
				format_money(award.committed, currency),
				note(
					off_boq.amount
						? __("Plus {0} ordered for the project outside the BOQ", [format_money(off_boq.amount, currency)])
						: award.project
						? __("Every order for the project traces to the BOQ")
						: __("Traced through the BOQ lines")
				)
			),
			kpi(
				__("Late purchase orders"),
				format_count(late),
				note(late ? __("Open orders past their delivery date") : __("Every open order is on time")),
				icon(late ? "critical" : "good", late ? "is-critical" : "is-good")
			),
			kpi(
				__("Shipments on the way"),
				format_count(shipments.length),
				note(shipments.length ? __("Not yet received") : __("Nothing in transit"))
			)
		)
	);
}

function render_components(components, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (!components.length) {
		card.append(el("p", { class: "ov-empty", text: __("No approved BOQ is linked to this award yet.") }));
		return card;
	}
	card.append(el("div", { class: "ov-list-legend" }, stage_legend()));
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			components.map((component) =>
				el(
					"li",
					{},
					form_link(
						"BOQ",
						component.boq,
						[
							el(
								"span",
								{ class: "ov-row-main" },
								el("span", { class: "ov-row-title", text: component.label }),
								el("span", {
									class: "ov-row-meta",
									text: [component.boq, component.components, __("{0} lines", [component.lines])]
										.filter(Boolean)
										.join(" · "),
								})
							),
							el("span", { class: "ov-progress-cell" }, render_stages(component, component.label), stage_figures(component)),
							el(
								"span",
								{ class: "ov-money-cell" },
								el("strong", { text: format_money(component.committed, currency) }),
								el("span", { text: __("of {0} budget", [format_money(component.budget, currency)]) })
							),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row ov-progress-row" }
					)
				)
			)
		)
	);
	return card;
}

function render_pending(lines, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (!lines.length) {
		card.append(el("p", { class: "ov-empty", text: __("Every approved BOQ line has been received.") }));
		return card;
	}
	const qty = (value, line) => (value ? format_qty(value, line.uom) : "—");
	card.append(
		render_table(
			[__("Item"), __("Component"), __("WBS"), __("To request"), __("To order"), __("To receive"), __("Budget")],
			lines.map((line) => [
				line.item_name || line.item_code,
				line.component || line.boq,
				line.wbs || "—",
				qty(line.to_request, line),
				qty(line.to_order, line),
				qty(line.to_receive, line),
				format_money(line.budget_amount, currency),
			])
		)
	);
	return card;
}

function render_late_orders(orders, currency) {
	return list_card(
		orders,
		__("No open order is past its delivery date."),
		(order) =>
			form_link(
				"Purchase Order",
				order.name,
				[
					icon("critical", "is-critical"),
					row_text(
						order.supplier,
						`${order.name} · ${__("due {0}", [format_date(order.schedule_date)])} · ${__("{0}% received", [
							Math.round(order.per_received || 0),
						])}`
					),
					el("span", {
						class: "ov-row-when is-late",
						text: order.days_late === 1 ? __("1 day late") : __("{0} days late", [order.days_late]),
					}),
					icon("chevron", "ov-chevron"),
				],
				{ class: "ov-row" }
			)
	);
}

function render_shipments(shipments) {
	return list_card(shipments, __("Nothing in transit for this award."), (shipment) =>
		form_link(
			"Shipment Tracking",
			shipment.name,
			[
				row_text(
					shipment.supplier || shipment.name,
					[shipment.name, __(shipment.status), shipment.purchase_order].filter(Boolean).join(" · ")
				),
				el("span", {
					class: "ov-row-when",
					text: shipment.expected_receipt_date
						? __("Expected {0}", [format_date(shipment.expected_receipt_date)])
						: __("No expected date"),
				}),
				icon("chevron", "ov-chevron"),
			],
			{ class: "ov-row" }
		)
	);
}

function render_documents(title, doctype, docs, describe) {
	const card = el("div", { class: "ov-card ov-list-card" }, el("h4", { class: "ov-list-title", text: title }));
	if (!docs.length) {
		card.append(el("p", { class: "ov-empty", text: __("None yet.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			docs.map((doc) => {
				const [main, meta, figure] = describe(doc);
				return el(
					"li",
					{},
					form_link(
						doctype,
						doc.name,
						[row_text(main, meta), figure ? el("span", { class: "ov-row-when", text: figure }) : null],
						{ class: "ov-row" }
					)
				);
			})
		)
	);
	return card;
}

function list_card(items, empty_text, row) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (!items.length) card.append(el("p", { class: "ov-empty", text: empty_text }));
	else card.append(el("ul", { class: "ov-rows" }, items.map((item) => el("li", {}, row(item)))));
	return card;
}

mount_view({
	api: "a3_constructa.api.award_procurement.get_award_procurement",
	args: { awarded_quotation: frappe.get_route()[1] || null },
	intro: __("How far each approved BOQ line has been requested, ordered and received."),
	render,
});
