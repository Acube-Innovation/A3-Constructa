// Delivery & Logistics Overview: tab 1 of the Delivery & Logistics workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Delivery & Logistics Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	const { shipments, receipts, currency } = data;
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Late shipments, held containers and missing paperwork"),
				body: render_health(data.health),
			}),
			section({
				title: __("Arriving next"),
				caption: __("Shipments on the way, the soonest due first"),
				body: render_arriving(shipments),
			})
		),
		section({
			title: __("Where shipments stand"),
			caption: __("Every shipment not yet received. Open a row to see those shipments."),
			body: el("div", { class: "ov-breakdowns" }, stages(shipments).map(render_breakdown)),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Top suppliers"),
				caption: __("Submitted purchase receipts over the last 12 months"),
				body: render_breakdown(suppliers(receipts, currency)),
			}),
			section({
				title: __("Where goods were received"),
				caption: __("Warehouse GRNs and site receipts over the last 12 months"),
				body: render_breakdown(destinations(receipts, currency)),
			})
		),
		el("p", {
			class: "ov-footnote",
			text: __("Money is shown in {0}, the company's default currency. Counts follow your permissions.", [
				currency,
			]),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { customs, costs, receipts, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_on_the_way(data.shipments, data.transit),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Received in the last 30 days"),
				receipts.restricted ? "—" : format_money(receipts.value_30d, currency),
				note(
					receipts.restricted
						? __("You do not have access to purchase receipts")
						: __("{0} into the warehouse · {1} at site", [receipts.warehouse_30d, receipts.site_30d])
				)
			),
			kpi(
				__("In port or customs"),
				customs.restricted ? "—" : format_count(customs.count),
				note(
					customs.restricted
						? __("You do not have access to shipments")
						: customs.count
						? __("The oldest arrived {0} days ago", [customs.oldest_days])
						: __("Nothing waiting at port")
				)
			),
			kpi(
				__("Demurrage & detention"),
				costs.restricted ? "—" : format_money(costs.total, currency),
				note(
					costs.restricted
						? __("You do not have access to shipments")
						: !costs.count
						? __("None in the last 12 months")
						: costs.count === 1
						? __("1 shipment, {0} demurrage days, last 12 months", [costs.days])
						: __("{0} shipments, {1} demurrage days, last 12 months", [costs.count, costs.days])
				)
			),
			health_kpi(data.health)
		)
	);
}

function render_on_the_way(shipments, transit) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("On the way") }));
	if (shipments.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to shipments.") }));
		return card;
	}
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: format_count(shipments.active) }),
			el("span", {
				class: "ov-hero-of",
				text: shipments.active === 1 ? __("shipment not yet received") : __("shipments not yet received"),
			})
		),
		el("p", {
			class: "ov-hero-caption",
			text: __("{0} import · {1} domestic", [shipments.import_count, shipments.domestic_count]),
		})
	);
	if (shipments.late_count) {
		card.append(
			el(
				"p",
				{ class: "ov-hero-issue" },
				icon("critical", "is-critical"),
				el("span", {
					text:
						shipments.late_count === 1
							? __("1 is past its expected receipt date")
							: __("{0} are past their expected receipt date", [shipments.late_count]),
				})
			)
		);
	}
	if (!transit.restricted && transit.count) {
		card.append(
			el(
				"div",
				{ class: "ov-hero-transit" },
				el("p", { class: "ov-label", text: __("Import transit, last 12 months") }),
				el(
					"p",
					{ class: "ov-hero-figure" },
					el("span", {
						class: "ov-hero-days",
						text: format_number(transit.average, null, Number.isInteger(transit.average) ? 0 : 1),
					}),
					el("span", {
						class: "ov-hero-of",
						text:
							transit.count === 1
								? __("days port to port, 1 shipment")
								: __("days port to port, average of {0} shipments", [transit.count]),
					})
				)
			)
		);
	}
	return card;
}

// ---------- Lists ----------

function render_arriving(shipments) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (shipments.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to shipments.") }));
		return card;
	}
	if (!shipments.arriving.length) {
		card.append(el("p", { class: "ov-empty", text: __("No shipments on the way.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			shipments.arriving.map((shipment) =>
				el(
					"li",
					{},
					form_link(
						"Shipment Tracking",
						shipment.name,
						[
							row_text(
								shipment.supplier,
								[shipment.name, __(shipment.status), __(shipment.shipment_type)].join(" · ")
							),
							el("span", {
								class: shipment.late ? "ov-row-when is-late" : "ov-row-when",
								text: shipment.due ? __("due {0}", [format_date(shipment.due)]) : __("no date set"),
							}),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row" }
					)
				)
			)
		)
	);
	return card;
}

// ---------- Breakdowns ----------

function stages(shipments) {
	const by = (title, field, rows, filters = {}) => ({
		title,
		doctype: "Shipment Tracking",
		field,
		filters: { ...shipments.filters, ...filters },
		restricted: shipments.restricted,
		rows: shipments.restricted ? [] : rows,
		total: shipments.restricted ? 0 : rows.reduce((sum, row) => sum + row.count, 0),
	});
	return [
		by(__("Imports by status"), "status", shipments.import_by_status || [], { shipment_type: "Import" }),
		by(__("Domestic by status"), "status", shipments.domestic_by_status || [], { shipment_type: "Domestic" }),
		by(__("By delivery mode"), "delivery_mode", shipments.by_mode || []),
		by(__("By project"), "project", shipments.by_project || []),
	];
}

function suppliers(receipts, currency) {
	return {
		title: __("By value received"),
		doctype: "Purchase Receipt",
		field: "supplier",
		filters: receipts.year_filters,
		restricted: receipts.restricted,
		measure: "amount",
		currency,
		rows: receipts.restricted ? [] : receipts.suppliers,
		total: receipts.restricted ? 0 : receipts.suppliers_total,
	};
}

function destinations(receipts, currency) {
	return {
		title: __("By destination"),
		doctype: "Purchase Receipt",
		field: "is_site_receipt",
		filters: receipts.year_filters,
		restricted: receipts.restricted,
		measure: "amount",
		currency,
		rows: receipts.restricted ? [] : receipts.by_destination,
		total: receipts.restricted ? 0 : receipts.destination_total,
	};
}

mount_overview({
	api: "a3_constructa.api.delivery_logistics_overview.get_overview",
	storage_key: "a3_constructa.delivery_logistics.tab",
	labels: { overview: __("Delivery & Logistics Overview"), menu: __("Delivery & Logistics") },
	intro: __("Shipments, customs, receipts and logistics costs across A3 Constructa."),
	render,
});
