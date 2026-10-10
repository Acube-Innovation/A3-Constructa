// Contracts & Awards Overview: tab 1 of the Contracts & Awards workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Contracts & Awards Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	const { currency } = data;
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Dates the client holds us to, and changes waiting on someone"),
				body: render_health(data.health),
			}),
			section({
				title: __("Milestones due"),
				caption: __("Overdue first, then the next {0} days", [data.milestones.window_days || 30]),
				body: render_milestones(data.milestones),
			})
		),
		section({
			title: __("Awards and variations"),
			caption: __("Open a row to see those records."),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(status_breakdown(data.awards, __("Awards by status"), "Awarded Quotation", null)),
				// Counted, not summed: money across approved, rejected and cancelled orders would mean nothing.
				render_breakdown(status_breakdown(data.variations, __("Variation orders by status"), "Variation Order", null))
			),
		}),
		section({
			title: __("Change and deliverables"),
			caption: __("Change events by where they came from, and the documents the client must approve"),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(source_breakdown(data.change_events, currency)),
				render_breakdown(status_breakdown(data.deliverables, __("Deliverables by status"), "Deliverable", null))
			),
		}),
		render_trend_section(data.trend, currency),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency; awards and variations in another currency are left out of the totals. Open change exposure counts Open, Priced and Claim change events. Counts follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { awards, variations, change_events: ce, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_order_book(awards, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Approved variations"),
				variations.restricted ? "—" : format_money(variations.approved_value, currency),
				note(
					variations.restricted
						? __("You do not have access to variation orders")
						: __("{0} orders approved", [variations.approved_count])
				)
			),
			kpi(
				__("Open change exposure"),
				ce.restricted ? "—" : format_money(ce.open_cost, currency),
				note(
					ce.restricted
						? __("You do not have access to change events")
						: !ce.open_count
						? __("Every change event is decided")
						: __("{0} events, {1} days at risk · {2} not priced", [ce.open_count, ce.open_days, ce.unpriced])
				)
			),
			kpi(
				__("Variations with the client"),
				variations.restricted ? "—" : format_count(variations.by_status.find((r) => r.value === "Submitted to Client")?.count || 0),
				note(
					variations.restricted
						? __("You do not have access to variation orders")
						: __("{0} waiting for an answer", [
								format_money(variations.by_status.find((r) => r.value === "Submitted to Client")?.amount || 0, currency),
						  ])
				)
			),
			health_kpi(data.health)
		)
	);
}

function render_order_book(awards, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Revised contract value") }));
	if (awards.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to awards.") }));
		return card;
	}
	if (!awards.active_count) {
		card.append(el("p", { class: "ov-hero-caption", text: __("No live award yet.") }));
		return card;
	}
	const share = awards.order_book ? Math.round((awards.original_value / awards.order_book) * 1000) / 10 : 0;
	card.append(
		el("p", { class: "ov-hero-figure" }, el("span", { class: "ov-hero-value", text: format_money(awards.order_book, currency) })),
		el(
			"div",
			{ class: "ov-stack-track", role: "img",
			  "aria-label": __("{0} original, {1} approved variations", [format_money(awards.original_value, currency), format_money(awards.approved_variations, currency)]) },
			el("span", { class: "ov-stack-original", style: `width: ${Math.min(share, 100)}%` }),
			el("span", { class: "ov-stack-variations", style: `width: ${Math.max(0, 100 - share)}%` })
		),
		el("p", {
			class: "ov-hero-caption",
			text: __("{0} awarded + {1} approved variations, across {2} live awards", [
				format_money(awards.original_value, currency),
				format_money(awards.approved_variations, currency),
				awards.active_count,
			]),
		}),
		report_link(
			"Variation Register",
			{ company: frappe.defaults.get_user_default("Company") },
			[el("span", { text: __("Open the variation register") }), icon("chevron", "ov-chevron")],
			{ class: "ov-hero-link" }
		)
	);
	return card;
}

// ---------- Milestones ----------

function render_milestones(milestones) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (milestones.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to awards.") }));
		return card;
	}
	if (!milestones.list.length) {
		card.append(el("p", { class: "ov-empty", text: __("Nothing overdue and nothing due in the next {0} days.", [milestones.window_days]) }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			milestones.list.map((row) =>
				el(
					"li",
					{},
					form_link(
						"Awarded Quotation",
						row.award,
						[
							row_text(row.milestone, `${row.award} · ${row.award_title || ""}`),
							el("span", {
								class: row.days < 0 ? "ov-row-when is-late" : "ov-row-when",
								text: row.days < 0 ? __("{0} days late", [-row.days]) : row.days === 0 ? __("Due today") : __("In {0} days", [row.days]),
								title: format_date(row.planned_end),
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

function status_breakdown(part, title, doctype, currency) {
	const rows = part.restricted ? [] : part.by_status;
	return {
		title,
		doctype,
		field: "status",
		filters: {},
		restricted: part.restricted,
		measure: currency ? "amount" : "count",
		currency,
		rows,
		total: rows.reduce((sum, row) => sum + (currency ? row.amount || 0 : row.count), 0),
	};
}

function source_breakdown(ce, currency) {
	const rows = ce.restricted ? [] : ce.by_source;
	return {
		title: __("Change events by source"),
		doctype: "Change Event",
		field: "source",
		filters: ce.restricted ? {} : ce.filters,
		restricted: ce.restricted,
		rows,
		total: rows.reduce((sum, row) => sum + row.count, 0),
	};
}

// ---------- Change raised and approved per month ----------

function render_trend_section(trend_part, currency) {
	const title = __("Change raised and approved per month");
	if (trend_part.restricted) {
		return section({
			title,
			caption: __("Change events and variation orders"),
			body: el("div", { class: "ov-card ov-chart-card" }, el("p", { class: "ov-empty", text: __("You do not have access to change events or variation orders.") })),
		});
	}
	const { trend } = trend_part;
	const raised = trend.reduce((sum, m) => sum + m.raised, 0);
	const approved = trend.reduce((sum, m) => sum + m.approved, 0);
	const chart = render_trend_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("Raised (rough cost)"), __("Events"), __("Approved (variations)"), __("Orders")],
		trend.map((m) => [m.label, format_money(m.raised, currency), format_count(m.raised_count), format_money(m.approved, currency), format_count(m.approved_count)])
	);
	table.classList.add("ov-trend-table");
	return section({
		title,
		caption: __("Last 12 months: {0} of change raised on site, {1} approved by the client as variations. An omission approved lowers its month.", [
			format_money(raised, currency),
			format_money(approved, currency),
		]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: raised || approved ? chart_with_table(chart, table) : null,
	});
}

// Paired columns per month: change raised (amber) beside variations approved (green).
// A month whose approvals net below zero (an omission) draws no green column; the
// tooltip and the table carry the figure.
function render_trend_chart(trend, currency) {
	const max = Math.max(0, ...trend.flatMap((m) => [m.raised, m.approved]));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No change raised or approved in the last 12 months.") });
	}
	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${trend.length}` });
	const legend = el(
		"div",
		{ class: "ov-legend ov-chart-legend" },
		el("span", {}, el("span", { class: "ov-swatch is-raised" }), el("span", { text: __("Raised") })),
		el("span", {}, el("span", { class: "ov-swatch is-approved" }), el("span", { text: __("Approved") }))
	);
	const plot = el("div", { class: "ov-plot" });
	for (let value = 0; value <= top; value += step) {
		plot.append(
			el(
				"div",
				{ class: value ? "ov-gridline" : "ov-gridline is-base", style: `top: ${100 - (value / top) * 100}%` },
				el("span", { class: "ov-tick", text: format_tick(value) })
			)
		);
	}
	const columns = el("div", { class: "ov-columns" });
	trend.forEach((m) => {
		const bar = (value, kind) =>
			el("div", {
				class: value > 0 ? `ov-col-bar is-${kind}` : `ov-col-bar is-${kind} is-zero`,
				style: `height: ${(Math.max(0, value) / top) * 100}%`,
			});
		const raised_bar = bar(m.raised, "raised");
		const approved_bar = bar(m.approved, "approved");
		const raised = format_money(m.raised, currency);
		const approved = format_money(m.approved, currency);
		const column = el(
			"div",
			{ class: "ov-col", tabindex: "0", role: "img", "aria-label": __("{0}: {1} raised, {2} approved", [m.label, raised, approved]) },
			el("div", { class: "ov-col-pair" }, raised_bar, approved_bar)
		);
		attach_tooltip(figure, column, m.raised >= m.approved ? raised_bar : approved_bar, __("{0} raised · {1} approved", [raised, approved]), m.label);
		columns.append(column);
	});
	plot.append(columns);
	figure.append(
		legend,
		plot,
		el(
			"div",
			{ class: "ov-xlabels", "aria-hidden": "true" },
			trend.map((m, index) => el("span", { text: index === 0 || m.month.endsWith("-01") ? `${m.short} ’${m.month.slice(2, 4)}` : m.short }))
		)
	);
	return figure;
}

mount_overview({
	api: "a3_constructa.api.contracts_awards_overview.get_overview",
	storage_key: "a3_constructa.contracts_awards.tab",
	labels: { overview: __("Contracts & Awards Overview"), menu: __("Contracts & Awards") },
	intro: __("What the jobs are worth today, the dates the clients hold us to, and the change still to settle."),
	render,
});
