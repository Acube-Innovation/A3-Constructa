// WBS Analysis & Reporting Overview: tab 1 of the WBS Analysis & Reporting workspace (D-13).
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "WBS Analysis & Reporting Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Every figure comes from the P-13 reports (api/wbs_analysis_overview.py), and
// every row opens the report it came from with the same filters.

function render(data) {
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Over budget, behind or over cost, unbilled work, slow trades and the alerts sent"),
				body: render_health(data.health),
			}),
			section({ title: __("Alerts sent, last 7 days"), caption: __("By the alert rules; each opens its record"), body: render_alerts(data.alerts) })
		),
		section({
			title: __("Cost and margin"),
			caption: __("Forecast against budget by cost head (Job Cost Report), and certified revenue against cost by project (Margin by WBS)."),
			body: el("div", { class: "ov-breakdowns" }, render_variance(data.variance, data.currency, data.company), render_margin(data.margin, data.currency, data.company)),
		}),
		section({
			title: __("Forecast and productivity"),
			caption: __("Budget at completion against the forecast (Earned Value), and planned ÷ actual hours by trade over the last 8 weeks."),
			body: el("div", { class: "ov-breakdowns" }, render_forecast_by_wbs(data.forecast_by_wbs, data.currency, data.company), render_trades(data.productivity, data.company)),
		}),
		render_curve_section(data.ev, data.currency, data.company),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Figures are read from the WBS Analysis reports for {0}, today. Money is in {1}, the company's default currency. A section you cannot run the report for is hidden. Counts follow your permissions.",
				[data.company, data.currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { ev, billing, over_budget, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_hero(data.forecast, currency, data.company),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Cost and schedule"),
				ev.restricted ? "—" : __("CPI {0}", [fmt_index(ev.cpi)]),
				note(ev.restricted ? __("You do not have access to the WBS reports") : __("SPI {0} · earned {1} of {2} planned", [fmt_index(ev.spi), format_money(ev.ev, currency), format_money(ev.pv, currency)])),
				ev.restricted ? null : icon(index_level(Math.min(ev.cpi ?? 1, ev.spi ?? 1)), `is-${index_level(Math.min(ev.cpi ?? 1, ev.spi ?? 1))}`)
			),
			kpi(
				__("Over-billed"),
				billing.restricted ? "—" : format_money(billing.over, currency),
				note(billing.restricted ? __("You do not have access to awards") : __("{0} under-billed · {1} billed of {2} earned", [format_money(billing.under, currency), format_money(billing.billed, currency), format_money(billing.earned, currency)]))
			),
			kpi(
				__("WBS over budget"),
				over_budget.restricted ? "—" : format_count(over_budget.count),
				note(over_budget.restricted ? __("You do not have access to the WBS") : over_budget.rows.length ? over_budget.rows.map((r) => __("{0} {1}% over", [r.name, r.percent])).join(" · ") : __("Every node within its budget"))
			),
			health_kpi(data.health)
		)
	);
}

function render_hero(forecast, currency, company) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Forecast margin at completion") }));
	if (forecast.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to the awards.") }));
		return card;
	}
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: format_money(forecast.margin, currency) }),
			el("span", { class: "ov-hero-of", text: forecast.percent === null ? "" : __("{0}% of {1}", [forecast.percent, format_money(forecast.contract, currency)]) })
		),
		el("p", {
			class: "ov-hero-caption",
			text: __("Revised contract value less the forecast cost (actual, committed and cost to complete), on the awards with a project.") +
				(forecast.without_forecast ? " " + __("{0} awards have no cost forecast yet.", [forecast.without_forecast]) : ""),
		}),
		el(
			"ul",
			{ class: "ov-project-rows" },
			forecast.awards.map((a) =>
				el(
					"li",
					{},
					report_link("WIP Schedule", { company, awarded_quotation: a.name }, [
						el("span", { class: "ov-project-name", text: a.label, title: a.label }),
						el("span", { class: a.margin < 0 ? "ov-behind" : "", text: a.percent === null ? format_money(a.margin, currency) : __("{0} · {1}%", [format_money(a.margin, currency), a.percent]) }),
					], { class: "ov-project-row" })
				)
			)
		),
		report_link("WIP Schedule", { company }, [el("span", { text: __("Open the WIP Schedule") }), icon("chevron", "ov-chevron")], { class: "ov-hero-link" })
	);
	return card;
}

function fmt_index(value) {
	return value === null || value === undefined ? "–" : Number(value).toFixed(2);
}

function index_level(value) {
	return value < 0.9 ? "critical" : value < 1 ? "warning" : "good";
}

// ---------- Alerts sent ----------

function render_alerts(alerts) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (alerts.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to alert rules.") }));
		return card;
	}
	if (!alerts.list.length) {
		card.append(el("p", { class: "ov-empty", text: __("No alerts sent in the last 7 days.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			alerts.list.map((a) =>
				el("li", {}, form_link(a.doctype, a.name, [row_text(a.detail || a.name, a.rule), el("span", { class: "ov-row-when", text: pretty_date(a.sent_on) }), icon("chevron", "ov-chevron")], { class: "ov-row" }))
			)
		)
	);
	return card;
}

// ---------- Signed bars: variance by cost head, margin by project ----------

function signed_card(title, total_text, rows, empty_text) {
	const card = el("div", { class: "ov-card ov-breakdown" }, el("div", { class: "ov-breakdown-head" }, el("h4", { class: "ov-breakdown-title", text: title }), total_text ? el("span", { class: "ov-breakdown-total", text: total_text }) : null));
	if (!rows.length) {
		card.append(el("p", { class: "ov-empty", text: empty_text }));
		return card;
	}
	const max = Math.max(...rows.map((r) => Math.abs(r.value))) || 1;
	const list = el("ul", { class: "ov-sbars" });
	rows.forEach((r) => {
		const share = Math.abs(r.value) / max;
		const bar = el("span", { class: r.value < 0 ? "ov-sbar is-negative" : "ov-sbar", style: `--ov-share: ${share}` });
		const link = r.open([
			el("span", { class: "ov-bar-label", text: r.label, title: r.label }),
			el("span", { class: "ov-sbar-track" }, el("span", { class: "ov-sbar-axis" }), bar),
			el("span", { class: r.value < 0 ? "ov-sbar-value ov-behind" : "ov-sbar-value", text: r.text }),
		], { class: "ov-sbar-row", "aria-label": `${r.label}: ${r.text}` });
		attach_tooltip(card, link, bar, r.text, r.detail);
		list.append(el("li", {}, link));
	});
	card.append(list);
	return card;
}

function render_variance(variance, currency, company) {
	if (variance.restricted) return restricted_card(__("Variance by cost head"), __("the WBS reports"));
	const total = variance.rows.reduce((s, r) => s + r.variance, 0);
	return signed_card(
		__("Variance by cost head"),
		__("{0} in total", [format_money(total, currency)]),
		variance.rows.map((r) => ({
			label: r.label,
			value: r.variance,
			text: format_money(r.variance, currency),
			detail: __("Budget {0} · forecast {1}", [format_money(r.revised, currency), format_money(r.forecast, currency)]),
			open: (content, attrs) => report_link("Job Cost Report", { company, depth: "Cost Head" }, content, attrs),
		})),
		__("No budget or cost yet.")
	);
}

function render_margin(margin, currency, company) {
	if (margin.restricted) return restricted_card(__("Margin by project"), __("the WBS reports"));
	const total = margin.rows.reduce((s, r) => s + r.margin, 0);
	return signed_card(
		__("Margin by project"),
		__("{0} in total", [format_money(total, currency)]),
		margin.rows.map((r) => ({
			label: r.label,
			value: r.margin,
			text: r.percent === null ? format_money(r.margin, currency) : `${format_money(r.margin, currency)} · ${r.percent}%`,
			detail: __("Revenue {0} · cost {1}", [format_money(r.revenue, currency), format_money(r.cost, currency)]),
			open: (content, attrs) => report_link("Margin by WBS", { company, project: r.project }, content, attrs),
		})),
		__("No certified revenue or cost yet.")
	);
}

function restricted_card(title, what) {
	return el("div", { class: "ov-card ov-breakdown" }, el("div", { class: "ov-breakdown-head" }, el("h4", { class: "ov-breakdown-title", text: title })), el("p", { class: "ov-empty", text: __("You do not have access to {0}", [what]) }));
}

// ---------- Forecast against budget by WBS ----------

function render_forecast_by_wbs(f, currency, company) {
	const title = __("Forecast against budget by WBS");
	if (f.restricted) return restricted_card(title, __("the WBS reports"));
	const card = el(
		"div",
		{ class: "ov-card ov-breakdown" },
		el("div", { class: "ov-breakdown-head" }, el("h4", { class: "ov-breakdown-title", text: title }),
			el("span", { class: "ov-legend" }, el("span", {}, el("span", { class: "ov-swatch is-budget" }), el("span", { text: __("Budget (BAC)") })), el("span", {}, el("span", { class: "ov-swatch is-forecast" }), el("span", { text: __("Forecast (EAC)") }))))
	);
	if (!f.rows.length) {
		card.append(el("p", { class: "ov-empty", text: __("No WBS with a budget yet.") }));
		return card;
	}
	const max = Math.max(...f.rows.map((r) => Math.max(r.bac, r.eac ?? 0)));
	const list = el("ul", { class: "ov-pairs" });
	f.rows.forEach((r) => {
		const over = r.eac !== null && r.eac > r.bac;
		const budget = el("span", { class: "ov-pair-bar is-budget", style: `--ov-share: ${r.bac / max}` });
		const spent_only = r.eac === null && r.ac > 0.005;
		const forecast = el("span", { class: r.eac === null ? (spent_only ? "ov-pair-bar is-forecast is-over" : "ov-pair-bar is-forecast is-none") : over ? "ov-pair-bar is-forecast is-over" : "ov-pair-bar is-forecast",
			style: `--ov-share: ${(r.eac ?? r.ac ?? 0) / max}` });
		// No forecast without a cost index: either nothing spent yet, or spent with nothing earned.
		const text = r.eac === null
			? (r.ac > 0.005 ? __("{0} spent, nothing earned", [format_money(r.ac, currency)]) : __("no cost yet"))
			: over ? __("{0} over", [format_money(r.eac - r.bac, currency)]) : __("{0} under", [format_money(r.bac - r.eac, currency)]);
		const link = report_link("Earned Value", { company, project: r.project, wbs: r.wbs }, [
			el("span", { class: "ov-bar-label", text: r.label, title: r.label }),
			el("span", { class: "ov-pair-track" }, budget, forecast),
			el("span", { class: over || spent_only ? "ov-sbar-value ov-behind" : "ov-sbar-value", text }),
		], { class: "ov-sbar-row", "aria-label": __("{0}: budget {1}, forecast {2}", [r.label, format_money(r.bac, currency), r.eac === null ? "–" : format_money(r.eac, currency)]) });
		attach_tooltip(card, link, forecast, r.eac === null ? "–" : format_money(r.eac, currency), __("Budget {0} · spent {1} · CPI {2}", [format_money(r.bac, currency), format_money(r.ac, currency), fmt_index(r.cpi)]));
		list.append(el("li", {}, link));
	});
	card.append(list);
	return card;
}

// ---------- Productivity by trade ----------

function render_trades(p, company) {
	const title = __("Productivity by trade, last 8 weeks");
	if (p.restricted) return restricted_card(title, __("timesheets"));
	const card = el("div", { class: "ov-card ov-breakdown" }, el("div", { class: "ov-breakdown-head" }, el("h4", { class: "ov-breakdown-title", text: title }), el("span", { class: "ov-breakdown-total", text: __("0.85 line marked") })));
	if (!p.trades.length) {
		card.append(el("p", { class: "ov-empty", text: __("No crew hours against planned output in the last 8 weeks.") }));
		return card;
	}
	const top = Math.max(1.25, ...p.trades.map((t) => t.factor || 0));
	const list = el("ul", { class: "ov-sbars" });
	p.trades.forEach((t) => {
		const low = t.factor !== null && t.factor < 0.85;
		const bar = el("span", { class: low ? "ov-fbar is-low" : "ov-fbar", style: `--ov-share: ${(t.factor || 0) / top}` });
		const link = report_link("Labour Productivity", { company, trade: t.value, from_date: p.from }, [
			el("span", { class: "ov-bar-label", text: t.label, title: t.label }),
			el("span", { class: "ov-fbar-track", style: `--ov-mark: ${0.85 / top}; --ov-one: ${1 / top}` }, bar, el("span", { class: "ov-fbar-mark", title: "0.85" }), el("span", { class: "ov-fbar-one", title: "1.00" })),
			el("span", { class: low ? "ov-sbar-value ov-behind" : "ov-sbar-value", text: fmt_index(t.factor) }),
		], { class: "ov-sbar-row", "aria-label": __("{0}: productivity factor {1}", [t.label, fmt_index(t.factor)]) });
		attach_tooltip(card, link, bar, fmt_index(t.factor), __("{0} h planned · {1} h worked · {2} of {3} weeks below 0.85", [t.planned, t.hours, t.low_weeks, t.weeks]));
		list.append(el("li", {}, link));
	});
	card.append(list);
	return card;
}

// ---------- S-curve ----------

function render_curve_section(ev, currency, company) {
	const title = __("S-curve: planned, earned and actual");
	if (ev.restricted) {
		return section({ title, caption: __("Earned Value"), body: el("div", { class: "ov-card ov-chart-card" }, el("p", { class: "ov-empty", text: __("You do not have access to the WBS reports.") })) });
	}
	const chart = render_curve(ev.curve, currency);
	const table = render_table([__("Month"), __("Planned (PV)"), __("Earned (EV)"), __("Actual (AC)")], ev.curve.map((p) => [p.label, format_money(p.pv, currency), format_money(p.ev, currency), format_money(p.ac, currency)]));
	table.classList.add("ov-trend-table");
	return section({
		title,
		caption: __("Cumulative, month by month, every project. Earned value runs {0} behind the plan (SPI {1}); cost {2} it (CPI {3}).",
			[format_money(Math.abs(ev.pv - ev.ev), currency), fmt_index(ev.spi), ev.ac > ev.ev ? __("runs ahead of") : __("stays within"), fmt_index(ev.cpi)]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table, report_link("Earned Value", { company, period: "Monthly" }, [el("span", { text: __("Open Earned Value") }), icon("chevron", "ov-chevron")], { class: "ov-hero-link ov-curve-link" })),
		action: ev.curve.length ? chart_with_table(chart, table) : null,
	});
}

function render_curve(points, currency) {
	if (!points.length) return el("p", { class: "ov-empty", text: __("No plan or cost yet.") });
	const max = Math.max(...points.flatMap((p) => [p.pv, p.ev, p.ac]));
	const { top, step } = nice_scale(max || 1);
	const W = 640, H = 200, n = points.length;
	const x = (i) => (n === 1 ? W / 2 : (i / (n - 1)) * W);
	const y = (v) => H - (Math.max(0, v) / top) * H;
	const ns = "http://www.w3.org/2000/svg";
	const svg = document.createElementNS(ns, "svg");
	svg.setAttribute("viewBox", `-56 -10 ${W + 72} ${H + 34}`);
	svg.setAttribute("class", "ov-curve");
	svg.setAttribute("role", "img");
	svg.setAttribute("aria-label", __("S-curve of planned value, earned value and actual cost"));
	const add = (tag, attrs, text) => {
		const node = document.createElementNS(ns, tag);
		Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
		if (text !== undefined) node.textContent = text;
		svg.append(node);
		return node;
	};
	for (let v = 0; v <= top; v += step) {
		add("line", { x1: 0, x2: W, y1: y(v), y2: y(v), class: v ? "ov-curve-grid" : "ov-curve-base" });
		add("text", { x: -8, y: y(v) + 4, class: "ov-curve-tick", "text-anchor": "end" }, format_tick(v));
	}
	points.forEach((p, i) => add("text", { x: x(i), y: H + 20, class: "ov-curve-tick", "text-anchor": "middle" }, p.label));
	[["pv", "is-pv"], ["ev", "is-ev"], ["ac", "is-ac"]].forEach(([key, cls]) => {
		add("polyline", { points: points.map((p, i) => `${x(i)},${y(p[key])}`).join(" "), class: `ov-curve-line ${cls}`, fill: "none" });
		points.forEach((p, i) => add("circle", { cx: x(i), cy: y(p[key]), r: 3, class: `ov-curve-dot ${cls}` }));
	});
	const legend = el("div", { class: "ov-legend ov-chart-legend" },
		[["is-pv", __("Planned value (PV)")], ["is-ev", __("Earned value (EV)")], ["is-ac", __("Actual cost (AC)")]].map(([cls, label]) => el("span", {}, el("span", { class: `ov-swatch ${cls}` }), el("span", { text: label }))));
	return el("figure", { class: "ov-chart" }, legend, svg);
}

mount_overview({
	api: "a3_constructa.api.wbs_analysis_overview.get_overview",
	storage_key: "a3_constructa.wbs_analysis.tab",
	labels: { overview: __("WBS Analysis & Reporting Overview"), menu: __("WBS Analysis & Reporting") },
	intro: __("Where the jobs stand on cost, schedule, billing and margin, read from the WBS analysis reports."),
	render,
});
