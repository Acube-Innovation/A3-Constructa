// Master Data Overview: tab 1 of the Master Data workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Master Data Overview" Custom HTML Block on every `bench migrate`
// (a3_constructa/setup/custom_html_blocks.py). Edit them here, not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	return [
		render_summary(data),
		section({
			title: __("Master areas"),
			caption: __("One tile for each card on the Master Data tab"),
			body: el("div", { class: "ov-areas" }, data.areas.map(render_area)),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Master records missing something they should have"),
				body: render_health(data.health),
			}),
			section({
				title: __("Recently added"),
				caption: __("The newest master records across all areas"),
				body: render_recent(data.recent),
			})
		),
		render_trend_section(data.trend),
		section({
			title: __("Composition"),
			caption: __("How the main masters are split"),
			body: el("div", { class: "ov-breakdowns" }, data.breakdowns.map(render_breakdown)),
		}),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Counts follow your permissions. Reference data that ERPNext loads at setup, such as currencies, countries and units, is not counted as activity."
			),
		}),
	];
}

// ---------- Sections ----------

function render_summary(data) {
	const areas = data.areas;
	const ready = areas.filter((area) => area.count > 0);
	const empty = areas.filter((area) => !area.restricted && area.count === 0);
	const share = areas.length ? ready.length / areas.length : 0;

	const hero = el(
		"div",
		{ class: "ov-card ov-hero" },
		el("p", { class: "ov-label", text: __("Setup coverage") }),
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: format_count(ready.length) }),
			el("span", { class: "ov-hero-of", text: __("of {0} master areas have records", [areas.length]) })
		),
		el(
			"div",
			{
				class: "ov-meter",
				role: "meter",
				"aria-label": __("Setup coverage"),
				"aria-valuemin": 0,
				"aria-valuemax": areas.length,
				"aria-valuenow": ready.length,
			},
			el("div", { class: "ov-meter-fill", style: `width: ${share * 100}%` })
		),
		render_still_empty(empty)
	);

	return el("div", { class: "ov-summary" }, hero, el("div", { class: "ov-kpis" }, render_kpis(data)));
}

function render_still_empty(empty) {
	if (!empty.length) {
		return el("p", { class: "ov-hero-caption", text: __("Every master area has records.") });
	}
	return el(
		"div",
		{ class: "ov-hero-todo" },
		el("p", { class: "ov-label", text: __("Not started yet") }),
		el(
			"ul",
			{ class: "ov-chips" },
			empty.map((area) => el("li", {}, list_link(area.doctype, area.filters, area.card, { class: "ov-chip" })))
		)
	);
}

function render_kpis(data) {
	const kpis = data.kpis;
	// The page's headline figure, on the dark panel.
	const added = kpi(
		__("Added in the last 30 days"),
		format_count(kpis.added_30d),
		delta_note(kpis.added_30d, kpis.added_prev_30d)
	);
	added.classList.add("ov-stat-panel");
	return [
		added,
		kpi(
			__("Edited in the last 30 days"),
			format_count(kpis.edited_30d),
			note(__("Records created before this period"))
		),
		kpi(
			__("Open projects"),
			kpis.active_projects === null ? "—" : format_count(kpis.active_projects),
			note(
				kpis.total_projects === null
					? __("You do not have access to projects")
					: __("{0} projects in total", [format_count(kpis.total_projects)])
			)
		),
		health_kpi(data.health),
	];
}

// Entry volume is neither good nor bad, so the delta stays in text colours.
function delta_note(current, previous) {
	const change = current - previous;
	if (!current && !previous) return note(__("None in the 30 days before either"));
	if (!change) return note(__("Same as the 30 days before"));
	return note(
		change > 0
			? __("{0} more than the 30 days before", [format_count(change)])
			: __("{0} fewer than the 30 days before", [format_count(-change)]),
		icon(change > 0 ? "up" : "down")
	);
}

function render_area(area) {
	const state = area.restricted ? "restricted" : area.count ? "ready" : "empty";
	const [status_icon, status_text, foot] = {
		ready: [
			icon("good", "is-good"),
			__("Has records"),
			area.last_modified ? __("Updated {0}", [pretty_date(area.last_modified)]) : "",
		],
		empty: [icon("empty", "is-muted"), __("No records yet"), __("Not started")],
		restricted: [icon("lock", "is-muted"), __("No access"), __("You do not have access to this area.")],
	}[state];

	const content = [
		el(
			"div",
			{ class: "ov-area-head" },
			el("span", { text: area.card }),
			el("span", { title: status_text }, status_icon, el("span", { class: "sr-only", text: status_text }))
		),
		el(
			"p",
			{ class: "ov-area-figure" },
			el("span", { class: "ov-area-count", text: area.restricted ? "—" : format_count(area.count) }),
			el("span", { class: "ov-area-unit", text: area.unit })
		),
		el(
			"ul",
			{ class: "ov-facts" },
			area.facts.map((fact) =>
				el(
					"li",
					{},
					el("span", { text: fact.label }),
					el("span", {
						class: "ov-fact-value",
						text: fact.count === null ? "—" : format_count(fact.count),
					})
				)
			)
		),
		el("p", { class: "ov-area-foot", text: foot }),
	];

	const attrs = { class: `ov-area is-${state}` };
	return area.restricted ? el("div", attrs, content) : list_link(area.doctype, area.filters, content, attrs);
}

function render_recent(rows) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (!rows.length) {
		card.append(el("p", { class: "ov-empty", text: __("No master records yet.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			rows.map((row) =>
				el(
					"li",
					{},
					form_link(
						row.doctype,
						row.name,
						[
							el("span", {
								class: "ov-initial",
								"aria-hidden": "true",
								text: (Array.from(String(row.title).trim())[0] || "?").toUpperCase(),
							}),
							row_text(
								row.title,
								[__(row.doctype), __("by {0}", [row.owner]), pretty_date(row.creation)].join(" · ")
							),
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

// ---------- Records added per month ----------

function render_trend_section(trend) {
	const total = trend.reduce((sum, point) => sum + point.count, 0);
	const chart = render_trend_chart(trend);
	const table = render_table(
		[__("Month"), __("Records added")],
		trend.map((point) => [point.label, format_count(point.count)])
	);
	const toggle = total ? chart_with_table(chart, table) : null;

	return section({
		title: __("Records added per month"),
		caption: __("{0} in the last 12 months", [format_count(total)]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: toggle,
	});
}

function render_trend_chart(trend) {
	const max = Math.max(0, ...trend.map((point) => point.count));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No master records were added in the last 12 months.") });
	}

	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${trend.length}` });
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

	// Label only the peak and the latest month; the tooltip and table carry the rest.
	const peak = trend.reduce((best, point, index) => (point.count > trend[best].count ? index : best), 0);
	const latest = trend.length - 1;
	const columns = el("div", { class: "ov-columns" });

	trend.forEach((point, index) => {
		const bar = el("div", {
			class: point.count ? "ov-col-bar" : "ov-col-bar is-zero",
			style: `height: ${(point.count / top) * 100}%`,
		});
		if (point.count && (index === peak || index === latest)) {
			bar.append(el("span", { class: "ov-col-cap", text: format_count(point.count) }));
		}
		const column = el(
			"div",
			{
				class: "ov-col",
				tabindex: "0",
				role: "img",
				"aria-label": __("{0}: {1} records added", [point.label, point.count]),
			},
			bar
		);
		attach_tooltip(figure, column, bar, format_count(point.count), point.label);
		columns.append(column);
	});

	plot.append(columns);
	figure.append(
		plot,
		el(
			"div",
			{ class: "ov-xlabels", "aria-hidden": "true" },
			trend.map((point, index) =>
				el("span", {
					// The first month and every January carry the year.
					text:
						index === 0 || point.month.endsWith("-01")
							? `${point.short} ’${point.month.slice(2, 4)}`
							: point.short,
				})
			)
		)
	);
	return figure;
}

mount_overview({
	api: "a3_constructa.api.master_data_overview.get_overview",
	storage_key: "a3_constructa.master_data.tab",
	labels: { overview: __("Master Data Overview"), menu: __("Master Data") },
	intro: __("A snapshot of the master data set up in A3 Constructa."),
	render,
});
