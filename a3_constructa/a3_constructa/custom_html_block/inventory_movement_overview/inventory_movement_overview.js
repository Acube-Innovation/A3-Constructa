// Inventory Movement Overview: tab 1 of the Inventory Movement workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Inventory Movement Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	const { stock, movements, currency } = data;
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Late transit, stock out of balance and late site requests"),
				body: render_health(data.health),
			}),
			section({
				title: __("Latest movements"),
				caption: __("Stock entries, the most recent first"),
				body: render_latest(movements, currency),
			})
		),
		section({
			title: __("How stock moved"),
			caption: __("Submitted stock entries over the last 90 days. Open a row to see those entries."),
			body: el("div", { class: "ov-breakdowns" }, flows(data).map(render_breakdown)),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Stock by warehouse"),
				caption: __("Value on hand in each warehouse"),
				body: render_breakdown(holdings(stock, currency, "warehouse")),
			}),
			section({
				title: __("Stock by item"),
				caption: __("The items holding the most value"),
				body: render_breakdown(holdings(stock, currency, "item_code")),
			})
		),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency, at stock valuation. Counts follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { stock, transit, issues, requests, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_on_hand(stock, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Dispatches in transit"),
				transit.restricted ? "—" : format_count(transit.count),
				note(transit_note(transit, stock, currency))
			),
			kpi(
				__("Issued to works, last 30 days"),
				issues.restricted ? "—" : format_money(issues.value_30d, currency),
				note(
					issues.restricted
						? __("You do not have access to stock entries")
						: !issues.count_30d && !issues.returns_30d
						? __("No material issued")
						: [
								issues.count_30d === 1 ? __("1 issue") : __("{0} issues", [issues.count_30d]),
								issues.returns_30d === 1
									? __("1 site return")
									: __("{0} site returns", [issues.returns_30d]),
						  ].join(" · ")
				)
			),
			kpi(
				__("Site requests open"),
				requests.restricted ? "—" : format_count(requests.open),
				note(
					requests.restricted
						? __("You do not have access to material requests")
						: !requests.open
						? __("Nothing waiting to be sent to site")
						: !requests.overdue
						? __("All within their required date")
						: requests.overdue === 1
						? __("1 is past its required date")
						: __("{0} are past their required date", [requests.overdue])
				)
			),
			health_kpi(data.health)
		)
	);
}

function transit_note(transit, stock, currency) {
	if (transit.restricted) return __("You do not have access to stock entries");
	if (!transit.count) return __("Nothing on the way");
	const sent =
		transit.count === 1
			? __("Sent {0}", [days_ago(transit.oldest_days)])
			: __("Oldest sent {0}", [days_ago(transit.oldest_days)]);
	const moving = stock.restricted ? null : stock.kinds.find((kind) => kind.key === "transit");
	return moving ? `${sent} · ${__("{0} on the way", [format_money(moving.amount, currency)])}` : sent;
}

function days_ago(days) {
	return !days ? __("today") : days === 1 ? __("1 day ago") : __("{0} days ago", [days]);
}

function render_on_hand(stock, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Stock on hand") }));
	if (stock.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to stock levels.") }));
		return card;
	}
	const items = stock.items === 1 ? __("1 item") : __("{0} items", [format_count(stock.items)]);
	const warehouses =
		stock.warehouses === 1 ? __("1 warehouse") : __("{0} warehouses", [format_count(stock.warehouses)]);
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: format_money(stock.value, currency) })
		),
		el("p", { class: "ov-hero-caption", text: __("{0} in stock across {1}", [items, warehouses]) })
	);
	if (stock.negative) {
		card.append(
			el(
				"p",
				{ class: "ov-hero-issue" },
				icon("critical", "is-critical"),
				el("span", {
					text:
						stock.negative === 1
							? __("1 stock balance is below zero")
							: __("{0} stock balances are below zero", [stock.negative]),
				})
			)
		);
	}
	if (stock.value > 0) card.append(render_mix(stock, currency));
	return card;
}

// Where the value sits, store to transit to site: one bar, and a legend whose
// rows open the stock lines behind them.
function render_mix(stock, currency) {
	const positive = stock.kinds.reduce((sum, kind) => sum + Math.max(0, kind.amount), 0);
	const share = (kind) => (positive ? Math.round((Math.max(0, kind.amount) / positive) * 100) : 0);
	return el(
		"div",
		{ class: "ov-mix" },
		el(
			"div",
			{
				class: "ov-mix-bar",
				role: "img",
				"aria-label": stock.kinds.map((kind) => `${kind.label} ${share(kind)}%`).join(", "),
			},
			stock.kinds.map((kind) =>
				el("span", {
					class: `ov-mix-part is-${kind.key}`,
					style: `flex-grow: ${Math.max(0, kind.amount)}`,
				})
			)
		),
		el(
			"ul",
			{ class: "ov-mix-legend" },
			stock.kinds.map((kind) =>
				el(
					"li",
					{},
					list_link(
						"Bin",
						kind.filters,
						[
							el("span", { class: `ov-swatch is-${kind.key}` }),
							el("span", { class: "ov-mix-label", text: kind.label }),
							el("span", { class: "ov-mix-value", text: format_money(kind.amount, currency) }),
							el("span", { class: "ov-mix-share", text: `${share(kind)}%` }),
						],
						{ class: "ov-mix-row" }
					)
				)
			)
		)
	);
}

// ---------- Lists ----------

function render_latest(movements, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (movements.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to stock entries.") }));
		return card;
	}
	if (!movements.latest.length) {
		card.append(el("p", { class: "ov-empty", text: __("No stock entries yet.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			movements.latest.map((entry) =>
				el(
					"li",
					{},
					form_link(
						"Stock Entry",
						entry.name,
						[
							row_text(
								entry.type ? __(entry.type) : __("Stock Entry"),
								[entry.draft ? __("Draft") : null, route_text(entry), entry.name]
									.filter(Boolean)
									.join(" · ")
							),
							el(
								"span",
								{ class: "ov-money-cell" },
								el("strong", { text: format_money(entry.amount, currency) }),
								el("span", { text: format_date(entry.date) })
							),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row ov-move-row" }
					)
				)
			)
		)
	);
	return card;
}

// "Central Store → Goods In Transit", or one side alone for a receipt or an issue.
function route_text(entry) {
	const side = (names) =>
		names.length > 1 ? __("{0} and {1} more", [names[0], names.length - 1]) : names[0] || null;
	const from = side(entry.from);
	const to = side(entry.to);
	if (from && to) return `${from} → ${to}`;
	if (from) return __("from {0}", [from]);
	if (to) return __("into {0}", [to]);
	return null;
}

// ---------- Breakdowns ----------

function flows(data) {
	const { movements, transit, issues, currency } = data;
	const by = (source, title, field, rows, total, filters, measure = "amount") => ({
		title,
		doctype: "Stock Entry",
		field,
		filters,
		restricted: source.restricted,
		measure,
		currency,
		rows: source.restricted ? [] : rows,
		total: source.restricted ? 0 : total,
	});
	return [
		by(movements, __("By movement type"), "stock_entry_type", movements.by_type, movements.type_total, movements.filters),
		by(
			transit,
			__("Dispatches by transport"),
			"mode_of_transport",
			transit.by_mode,
			transit.mode_total,
			transit.mode_filters,
			"count"
		),
		by(issues, __("Material issued by WBS"), "wbs", issues.by_wbs, issues.wbs_total, issues.filters),
		by(
			issues,
			__("Material issued by cost code"),
			"cost_code",
			issues.by_cost_code,
			issues.cost_code_total,
			issues.filters
		),
	];
}

function holdings(stock, currency, field) {
	return {
		title: field === "warehouse" ? __("By value on hand") : __("Top items by value"),
		doctype: "Bin",
		field,
		filters: stock.filters,
		restricted: stock.restricted,
		measure: "amount",
		currency,
		rows: stock.restricted ? [] : field === "warehouse" ? stock.by_warehouse : stock.by_item,
		total: stock.restricted ? 0 : field === "warehouse" ? stock.warehouse_total : stock.item_total,
	};
}

mount_overview({
	api: "a3_constructa.api.inventory_movement_overview.get_overview",
	storage_key: "a3_constructa.inventory_movement.tab",
	labels: { overview: __("Inventory Movement Overview"), menu: __("Inventory Movement") },
	intro: __("Stock on hand, transit, site receipts and issues to the works across A3 Constructa."),
	render,
});
