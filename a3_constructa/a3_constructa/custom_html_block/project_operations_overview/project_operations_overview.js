// Project Operations Overview: tab 1 of the Project Operations workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Project Operations Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Late work, missing site reports and what's holding the next weeks up"),
				body: render_health(data.health),
			}),
			section({
				title: __("Critical tasks, next 7 days"),
				caption: __("On the critical path, or late enough to move the finish"),
				body: render_critical(data.critical),
			})
		),
		section({
			title: __("Tasks and delays"),
			caption: __("Open a row to see those records."),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(task_breakdown(data.tasks)),
				render_breakdown(delay_breakdown(data.delays))
			),
		}),
		section({
			title: __("Quality and handover"),
			caption: __("Non-conformances still open, by WBS, and snags not yet verified, by trade"),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(ncr_breakdown(data.ncrs, data.currency)),
				render_breakdown(snag_breakdown(data.snags))
			),
		}),
		render_labour_section(data.labour),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Progress is the WBS roll-up, weighted by budget; planned is where the baseline says the work should be today. Money is shown in {0}, the company's default currency. Counts follow your permissions.",
				[data.currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { week, ncrs, snags, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_progress(data.progress),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Starting this week"),
				week.restricted ? "—" : format_count(week.starting),
				note(
					week.restricted
						? __("You do not have access to tasks")
						: __("{0} of them Ready on the look-ahead", [week.ready])
				)
			),
			kpi(
				__("Open NCRs"),
				ncrs.restricted ? "—" : format_count(ncrs.open),
				note(
					ncrs.restricted
						? __("You do not have access to non-conformances")
						: __("{0} overdue · {1} cost impact", [ncrs.overdue, format_money(ncrs.cost, currency)])
				)
			),
			kpi(
				__("Open snags"),
				snags.restricted ? "—" : format_count(snags.open + snags.fixed),
				note(
					snags.restricted
						? __("You do not have access to snag lists")
						: __("{0} open, {1} fixed awaiting check", [snags.open, snags.fixed])
				)
			),
			health_kpi(data.health)
		)
	);
}

function render_progress(progress) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Complete, against planned") }));
	if (progress.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to tasks and the WBS.") }));
		return card;
	}
	const behind = Math.round((progress.planned - progress.percent) * 10) / 10;
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: `${progress.percent}%` }),
			el("span", { class: "ov-hero-of", text: __("of {0}% planned", [progress.planned]) })
		),
		meter(progress.percent, progress.planned, __("{0}% complete, {1}% planned", [progress.percent, progress.planned])),
		el("p", {
			class: "ov-hero-caption",
			text: behind > 0
				? __("{0} points behind the baseline across the open projects, weighted by budget", [behind])
				: __("On or ahead of the baseline across the open projects"),
		}),
		el(
			"ul",
			{ class: "ov-project-rows" },
			progress.projects.map((p) =>
				el(
					"li",
					{ class: "ov-project-row" },
					el("span", { class: "ov-project-name", text: p.label, title: p.label }),
					el("span", { class: p.planned - p.percent > 0.05 ? "ov-behind" : "", text: __("{0}% / {1}%", [p.percent, p.planned]) }),
					meter(p.percent, p.planned, __("{0}: {1}% complete, {2}% planned", [p.label, p.percent, p.planned]))
				)
			)
		),
		report_link("WBS Progress", {}, [el("span", { text: __("Open WBS Progress") }), icon("chevron", "ov-chevron")], { class: "ov-hero-link" })
	);
	return card;
}

function meter(percent, planned, label) {
	return el(
		"div",
		{ class: "ov-meter ov-plan-meter", role: "img", "aria-label": label },
		el("div", { class: "ov-meter-fill", style: `width: ${Math.min(100, Math.max(0, percent))}%` }),
		el("span", { class: "ov-plan-mark", style: `left: calc(${Math.min(100, Math.max(0, planned))}% - 1px)`, title: __("Planned") })
	);
}

// ---------- Critical tasks ----------

function render_critical(critical) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (critical.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to tasks.") }));
		return card;
	}
	if (!critical.list.length) {
		card.append(el("p", { class: "ov-empty", text: __("No critical work in the next 7 days.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			critical.list.map((t) =>
				el(
					"li",
					{},
					form_link(
						"Task",
						t.name,
						[
							row_text(
								t.subject,
								[
									t.project,
									t.starting ? __("starts {0}", [pretty_date(t.start)]) : __("{0}% done", [t.progress]),
									t.late ? __("forecast {0}", [pretty_date(t.forecast)]) : __("due {0}", [pretty_date(t.end)]),
								].join(" · ")
							),
							el("span", {
								class: t.late ? "ov-row-when ov-behind" : "ov-row-when",
								text: t.late ? __("Finish +{0} days", [t.late]) : t.starting ? __("Starting") : __("On time"),
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

function task_breakdown(tasks) {
	const rows = tasks.restricted ? [] : tasks.by_status;
	return {
		title: __("Tasks by status"),
		doctype: "Task",
		field: "status",
		filters: tasks.restricted ? {} : tasks.filters,
		restricted: tasks.restricted,
		rows,
		total: tasks.restricted ? 0 : tasks.total,
	};
}

function delay_breakdown(delays) {
	const rows = delays.restricted ? [] : delays.by_cause;
	return {
		title: __("Hours lost by cause, last 30 days"),
		doctype: "Daily Site Report",
		field: "name",
		filters: {},
		restricted: delays.restricted,
		rows: rows.map((r) => ({ ...r, count: r.amount })),
		total: delays.restricted ? 0 : delays.hours,
	};
}

function ncr_breakdown(ncrs, currency) {
	const rows = ncrs.restricted ? [] : ncrs.by_wbs;
	return {
		title: __("Open NCRs by WBS"),
		doctype: "Non Conformance",
		field: "wbs",
		filters: ncrs.restricted ? {} : ncrs.filters,
		restricted: ncrs.restricted,
		currency,
		rows,
		total: ncrs.restricted ? 0 : ncrs.open,
	};
}

function snag_breakdown(snags) {
	const rows = snags.restricted ? [] : snags.by_trade;
	return {
		title: __("Snags not yet verified, by trade"),
		doctype: "Snag List",
		field: "name",
		filters: {},
		restricted: snags.restricted,
		rows,
		total: snags.restricted ? 0 : snags.open + snags.fixed,
	};
}

// ---------- Labour on site per week ----------

function render_labour_section(labour) {
	const title = __("Labour on site per week");
	if (labour.restricted) {
		return section({
			title,
			caption: __("From the filed daily site reports"),
			body: el("div", { class: "ov-card ov-chart-card" }, el("p", { class: "ov-empty", text: __("You do not have access to daily site reports.") })),
		});
	}
	const { weeks } = labour;
	const hours = weeks.reduce((sum, w) => sum + w.hours, 0);
	const lost = weeks.reduce((sum, w) => sum + w.lost, 0);
	const chart = render_labour_chart(weeks);
	const table = render_table(
		[__("Week of"), __("Labour hours"), __("Hours lost"), __("Reports")],
		weeks.map((w) => [w.label, format_count(w.hours), format_count(w.lost), format_count(w.reports)])
	);
	table.classList.add("ov-trend-table");
	return section({
		title,
		caption: __("Last 12 weeks: {0} labour hours booked from the daily site reports, {1} hours lost to delays.", [format_count(hours), format_count(lost)]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: hours ? chart_with_table(chart, table) : null,
	});
}

function render_labour_chart(weeks) {
	const max = Math.max(0, ...weeks.map((w) => w.hours));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No site reports filed in the last 12 weeks.") });
	}
	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${weeks.length}` });
	const legend = el(
		"div",
		{ class: "ov-legend ov-chart-legend" },
		el("span", {}, el("span", { class: "ov-swatch is-hours" }), el("span", { text: __("Labour hours") })),
		el("span", {}, el("span", { class: "ov-swatch is-lost" }), el("span", { text: __("Hours lost") }))
	);
	const plot = el("div", { class: "ov-plot" });
	for (let value = 0; value <= top; value += step) {
		plot.append(
			el("div", { class: value ? "ov-gridline" : "ov-gridline is-base", style: `top: ${100 - (value / top) * 100}%` },
				el("span", { class: "ov-tick", text: format_tick(value) }))
		);
	}
	const columns = el("div", { class: "ov-columns" });
	weeks.forEach((w) => {
		const bar = (value, kind) =>
			el("div", { class: value > 0 ? `ov-col-bar is-${kind}` : `ov-col-bar is-${kind} is-zero`, style: `height: ${(Math.max(0, value) / top) * 100}%` });
		const hours_bar = bar(w.hours, "hours");
		const lost_bar = bar(w.lost, "lost");
		const column = el(
			"div",
			{ class: "ov-col", tabindex: "0", role: "img", "aria-label": __("Week of {0}: {1} labour hours, {2} lost", [w.label, w.hours, w.lost]) },
			el("div", { class: "ov-col-pair" }, hours_bar, lost_bar)
		);
		attach_tooltip(figure, column, hours_bar, __("{0} h · {1} h lost", [format_count(w.hours), format_count(w.lost)]), __("Week of {0}", [w.label]));
		columns.append(column);
	});
	plot.append(columns);
	figure.append(legend, plot, el("div", { class: "ov-xlabels", "aria-hidden": "true" }, weeks.map((w) => el("span", { text: w.label }))));
	return figure;
}

mount_overview({
	api: "a3_constructa.api.project_operations_overview.get_overview",
	storage_key: "a3_constructa.project_operations.tab",
	labels: { overview: __("Project Operations Overview"), menu: __("Project Operations") },
	intro: __("Where the jobs stand against their programmes, what's holding the next weeks up, and the quality and handover still open."),
	render,
});
