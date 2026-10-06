// CRM & Estimating Overview: tab 1 of the CRM & Estimating workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "CRM & Estimating Overview" Custom HTML Block on every
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
				caption: __("Tenders, prices and bids that need someone to act"),
				body: render_health(data.health),
			}),
			section({
				title: __("Tenders due next"),
				caption: __("Open opportunities by tender due date"),
				body: render_tenders(data.tenders, currency),
			})
		),
		section({
			title: __("Pipeline"),
			caption: __("Open opportunities by value. Open a row to see them."),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(opportunity_breakdown(data.by_stage, __("By sales stage"), "sales_stage", currency)),
				render_breakdown(opportunity_breakdown(data.by_sector, __("By sector"), "sector", currency))
			),
		}),
		section({
			title: __("Quotations"),
			caption: __("Where every live quotation stands, and why bids were lost in the last 12 months"),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(quotation_breakdown(data.quotation_status, __("By status"))),
				render_breakdown(quotation_breakdown(data.lost_reasons, __("Lost reasons")))
			),
		}),
		render_trend_section(data.trend, currency),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency. Pipeline value is the opportunity amount, or its estimated value before it is priced. Won means a sales order or an award names the quotation. Counts follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { pipeline, tenders, awaiting, win_rate, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_pipeline(pipeline, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Tenders due in 14 days"),
				tenders.restricted ? "—" : format_count(tenders.due_count),
				note(
					tenders.restricted
						? __("You do not have access to opportunities")
						: !tenders.due_count
						? __("No tender falls due in the next two weeks")
						: tenders.unquoted
						? __("{0} not quoted yet", [tenders.unquoted])
						: __("All of them quoted")
				)
			),
			kpi(
				__("Quotations awaiting a decision"),
				awaiting.restricted ? "—" : format_count(awaiting.count),
				note(
					awaiting.restricted
						? __("You do not have access to quotations")
						: awaiting.count
						? __("{0} with clients", [format_money(awaiting.value, currency)])
						: __("No quotation is waiting on a client")
				)
			),
			kpi(
				__("Win rate, 12 months"),
				win_rate.restricted || win_rate.percent === null ? "—" : `${format_number(win_rate.percent, null, 0)}%`,
				note(
					win_rate.restricted
						? __("You do not have access to quotations")
						: win_rate.percent === null
						? __("No bid decided in the last 12 months")
						: __("{0} won, {1} lost · {2}% by value", [
								win_rate.won,
								win_rate.lost,
								format_number(win_rate.value_percent || 0, null, 0),
						  ])
				)
			),
			health_kpi(data.health)
		)
	);
}

function render_pipeline(pipeline, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Weighted pipeline") }));
	if (pipeline.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to opportunities.") }));
		return card;
	}
	if (!pipeline.count) {
		card.append(el("p", { class: "ov-hero-caption", text: __("No open opportunity yet.") }));
		return card;
	}
	const share = pipeline.value ? Math.round((pipeline.weighted / pipeline.value) * 100) : 0;
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: format_money(pipeline.weighted, currency) })
		),
		el(
			"div",
			{
				class: "ov-weight-track",
				role: "meter",
				"aria-valuemin": "0",
				"aria-valuemax": "100",
				"aria-valuenow": String(share),
				"aria-label": __("Weighted share of the pipeline"),
			},
			el("span", { class: "ov-weight-fill", style: `width: ${Math.min(share, 100)}%` })
		),
		el("p", {
			class: "ov-hero-caption",
			text: [
				__("{0}% of {1} across {2} open opportunities, by their probability of award", [
					share,
					format_money(pipeline.value, currency),
					pipeline.count,
				]),
				pipeline.leads ? __("{0} more leads not yet qualified", [pipeline.leads]) : null,
			]
				.filter(Boolean)
				.join(" · "),
		}),
		report_link(
			"Opportunity Pipeline",
			{ company: frappe.defaults.get_user_default("Company") },
			[el("span", { text: __("Open the pipeline report") }), icon("chevron", "ov-chevron")],
			{ class: "ov-hero-link" }
		)
	);
	return card;
}

// ---------- Tenders due next ----------

function render_tenders(tenders, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (tenders.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to opportunities.") }));
		return card;
	}
	if (!tenders.next.length) {
		card.append(el("p", { class: "ov-empty", text: __("No open tender has a due date ahead.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			tenders.next.map((row) =>
				el(
					"li",
					{},
					form_link(
						"Opportunity",
						row.name,
						[
							row_text(
								row.title,
								[
									row.quoted ? __("Quoted") : __("Not quoted"),
									format_money(row.value, currency),
									row.sector ? __(row.sector) : null,
								]
									.filter(Boolean)
									.join(" · ")
							),
							el("span", {
								class: !row.quoted && row.days <= 7 ? "ov-row-when is-late" : "ov-row-when",
								text: due_text(row),
								title: format_date(row.due),
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

function due_text(row) {
	if (row.days === 0) return __("Due today");
	if (row.days === 1) return __("Due tomorrow");
	return __("In {0} days", [row.days]);
}

// ---------- Breakdowns ----------

function opportunity_breakdown(part, title, field, currency) {
	return {
		title,
		doctype: "Opportunity",
		field,
		filters: part.filters,
		restricted: part.restricted,
		measure: "amount",
		currency,
		rows: part.restricted ? [] : part.rows,
		total: part.restricted ? 0 : part.total,
	};
}

// Each row carries the names it counts, so its link reproduces the count.
function quotation_breakdown(part, title) {
	return {
		title,
		doctype: "Quotation",
		field: "name",
		filters: {},
		restricted: part.restricted,
		rows: part.restricted ? [] : part.rows,
		total: part.restricted ? 0 : part.total,
	};
}

// ---------- Won and lost per month ----------

function render_trend_section(trend_part, currency) {
	const title = __("Won and lost per month");
	if (trend_part.restricted) {
		return section({
			title,
			caption: __("Decided quotations, by quotation date"),
			body: el(
				"div",
				{ class: "ov-card ov-chart-card" },
				el("p", { class: "ov-empty", text: __("You do not have access to quotations.") })
			),
		});
	}
	const { trend } = trend_part;
	const won = trend.reduce((sum, m) => sum + m.won, 0);
	const lost = trend.reduce((sum, m) => sum + m.lost, 0);
	const chart = render_trend_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("Won"), __("Lost"), __("Bids decided")],
		trend.map((m) => [
			m.label,
			format_money(m.won, currency),
			format_money(m.lost, currency),
			format_count(m.won_count + m.lost_count),
		])
	);
	table.classList.add("ov-trend-table");
	return section({
		title,
		caption: __("Decided quotations by quotation date, last 12 months: {0} won, {1} lost", [
			format_money(won, currency),
			format_money(lost, currency),
		]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: won || lost ? chart_with_table(chart, table) : null,
	});
}

// Paired columns per month: won (green) beside lost (red).
function render_trend_chart(trend, currency) {
	const max = Math.max(0, ...trend.flatMap((m) => [m.won, m.lost]));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No bid was won or lost in the last 12 months.") });
	}
	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${trend.length}` });
	const legend = el(
		"div",
		{ class: "ov-legend ov-chart-legend" },
		el("span", {}, el("span", { class: "ov-swatch is-won" }), el("span", { text: __("Won") })),
		el("span", {}, el("span", { class: "ov-swatch is-lost" }), el("span", { text: __("Lost") }))
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
		const bar = (key, kind) =>
			el("div", {
				class: m[key] ? `ov-col-bar is-${kind}` : `ov-col-bar is-${kind} is-zero`,
				style: `height: ${(m[key] / top) * 100}%`,
			});
		const bar_won = bar("won", "won");
		const bar_lost = bar("lost", "lost");
		const won = format_money(m.won, currency);
		const lost = format_money(m.lost, currency);
		const column = el(
			"div",
			{ class: "ov-col", tabindex: "0", role: "img", "aria-label": __("{0}: {1} won, {2} lost", [m.label, won, lost]) },
			el("div", { class: "ov-col-pair" }, bar_won, bar_lost)
		);
		attach_tooltip(figure, column, m.won >= m.lost ? bar_won : bar_lost, __("{0} won · {1} lost", [won, lost]), m.label);
		columns.append(column);
	});
	plot.append(columns);
	figure.append(
		legend,
		plot,
		el(
			"div",
			{ class: "ov-xlabels", "aria-hidden": "true" },
			trend.map((m, index) =>
				el("span", { text: index === 0 || m.month.endsWith("-01") ? `${m.short} ’${m.month.slice(2, 4)}` : m.short })
			)
		)
	);
	return figure;
}

mount_overview({
	api: "a3_constructa.api.crm_estimating_overview.get_overview",
	storage_key: "a3_constructa.crm_estimating.tab",
	labels: { overview: __("CRM & Estimating Overview"), menu: __("CRM & Estimating") },
	intro: __("The tenders being chased, the quotations with clients, and how bids have ended."),
	render,
});
