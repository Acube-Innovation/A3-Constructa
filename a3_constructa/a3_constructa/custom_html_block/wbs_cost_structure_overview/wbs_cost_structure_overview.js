// WBS & Cost Structure Overview: tab 1 of the WBS & Cost Structure workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "WBS & Cost Structure Overview" Custom HTML Block on every
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
				caption: __("Budget not yet on the works, stuck documents and loose ends"),
				body: render_health(data.health),
			}),
			section({
				title: __("Recent budget changes"),
				caption: __("The latest rows of the Budget Revision Log"),
				body: render_recent(data.changes, currency),
			})
		),
		section({
			title: __("Where the budget sits"),
			caption: __("The approved BOQ budget. Open a row to see its BOQs or cost codes."),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(by_head(data.budget_by_head, currency)),
				render_breakdown(by_category(data.budget_by_category, currency))
			),
		}),
		section({
			title: __("WBS nodes"),
			caption: __("Every node of the company's projects. Open a row to see those nodes."),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(wbs_breakdown(data.wbs, __("By status"), "status", "by_status")),
				render_breakdown(wbs_breakdown(data.wbs, __("By node type"), "node_type", "by_type"))
			),
		}),
		render_trend_section(data.changes, currency),
		el("p", {
			class: "ov-footnote",
			text: __("Money is shown in {0}, the company's default currency. Counts follow your permissions.", [currency]),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { allocation, wbs, changes, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_allocated(allocation, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Unallocated balance"),
				allocation.restricted ? "—" : format_money(allocation.unallocated, currency),
				note(
					allocation.restricted
						? __("You do not have access to BOQs and allocations")
						: allocation.lines_open
						? __("{0} BOQ lines still open · {1} of it in allowances", [
								allocation.lines_open,
								format_money(allocation.allowances_left, currency),
						  ])
						: __("Every approved line is allocated")
				)
			),
			kpi(
				__("Active WBS nodes"),
				wbs.restricted ? "—" : format_count(wbs.active),
				note(wbs.restricted ? __("You do not have access to WBS") : status_note(wbs))
			),
			kpi(
				__("Budget changes this month"),
				changes.restricted ? "—" : format_count(changes.this_month.count),
				note(
					changes.restricted
						? __("You do not have access to the Budget Revision Log")
						: !changes.this_month.count
						? __("No change to any budget yet this month")
						: Math.abs(changes.this_month.net) < 0.005
						? __("Budget moved between nodes; the total is unchanged")
						: __("Net {0} this month", [signed_money(changes.this_month.net, currency)])
				)
			),
			health_kpi(data.health)
		)
	);
}

function status_note(wbs) {
	const others = wbs.by_status.filter((row) => row.value !== "Active").map((row) => `${row.count} ${row.label}`);
	return others.length
		? __("of {0} nodes · {1}", [wbs.total, others.join(" · ")])
		: __("All {0} nodes are Active", [wbs.total]);
}

function render_allocated(allocation, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Approved budget on the works") }));
	if (allocation.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to BOQs and allocations.") }));
		return card;
	}
	if (!allocation.approved) {
		card.append(el("p", { class: "ov-hero-caption", text: __("No BOQ has been approved yet.") }));
		return card;
	}
	const percent = allocation.percent || 0;
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value", text: `${format_number(percent, null, percent % 1 ? 1 : 0)}%` }),
			el("span", { class: "ov-hero-of", text: __("of the approved BOQ allocated to WBS") })
		),
		el(
			"div",
			{
				class: "ov-alloc-track",
				role: "meter",
				"aria-valuemin": "0",
				"aria-valuemax": "100",
				"aria-valuenow": String(percent),
				"aria-label": __("Allocated share of the approved BOQ"),
			},
			el("span", { class: "ov-alloc-fill", style: `width: ${Math.min(percent, 100)}%` })
		),
		el("p", {
			class: "ov-hero-caption",
			text: __("{0} of {1} allocated, across {2} approved BOQs", [
				format_money(allocation.allocated, currency),
				format_money(allocation.approved, currency),
				allocation.boqs,
			]),
		}),
		report_link(
			"Unallocated BOQ Lines",
			{ company: frappe.defaults.get_user_default("Company") },
			[el("span", { text: __("See what is left to allocate") }), icon("chevron", "ov-chevron")],
			{ class: "ov-hero-link" }
		)
	);
	return card;
}

// ---------- Recent changes ----------

const CHANGE_LABELS = {
	Original: __("Original"),
	"BOQ Revision": __("BOQ revision"),
	Variation: __("Variation"),
	"Transfer In": __("Transfer in"),
	"Transfer Out": __("Transfer out"),
};

function render_recent(changes, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (changes.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to the Budget Revision Log.") }));
		return card;
	}
	if (!changes.recent.length) {
		card.append(el("p", { class: "ov-empty", text: __("No budget changes in the last 12 months.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			changes.recent.map((row) =>
				el(
					"li",
					{},
					form_link(
						row.reference_doctype || "Budget Revision Log",
						row.reference_name || row.name,
						[
							row_text(
								`${CHANGE_LABELS[row.change_type] || row.change_type} · ${row.wbs || __("no WBS")}`,
								[row.reference_name, row.cost_code, format_date(row.posted_on)].filter(Boolean).join(" · ")
							),
							el("span", {
								class: row.amount < 0 ? "ov-row-when is-late" : "ov-row-when",
								text: signed_money(row.amount, currency),
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

function signed_money(value, currency) {
	const text = format_money(Math.abs(value), currency);
	return value < 0 ? `−${text}` : value > 0 ? `+${text}` : text;
}

// ---------- Breakdowns ----------

function by_head(budget, currency) {
	return {
		title: __("By cost head"),
		doctype: "BOQ",
		field: "cost_head",
		filters: budget.filters,
		restricted: budget.restricted,
		measure: "amount",
		currency,
		rows: budget.restricted ? [] : budget.rows,
		total: budget.restricted ? 0 : budget.total,
	};
}

function by_category(budget, currency) {
	return {
		title: __("By cost code category"),
		doctype: "Cost Code",
		field: "category",
		filters: {},
		restricted: budget.restricted,
		measure: "amount",
		currency,
		rows: budget.restricted ? [] : budget.rows,
		total: budget.restricted ? 0 : budget.total,
	};
}

function wbs_breakdown(wbs, title, field, key) {
	const rows = wbs.restricted ? [] : wbs[key];
	return {
		title,
		doctype: "WBS",
		field,
		filters: wbs.filters,
		restricted: wbs.restricted,
		rows,
		total: rows.reduce((sum, row) => sum + row.count, 0),
	};
}

// ---------- Budget changes per month ----------

// Additions rise above the baseline, removals fall below it, so a revision
// that takes budget away reads as a drop rather than as more activity.
function render_trend_section(changes, currency) {
	if (changes.restricted) {
		return section({
			title: __("Budget changes per month"),
			caption: __("From the Budget Revision Log"),
			body: el("div", { class: "ov-card ov-chart-card" }, el("p", { class: "ov-empty", text: __("You do not have access to the Budget Revision Log.") })),
		});
	}
	const trend = changes.trend;
	const added = trend.reduce((sum, m) => sum + m.added, 0);
	const removed = trend.reduce((sum, m) => sum + m.removed, 0);
	const chart = render_change_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("Added"), __("Removed"), __("Net"), __("Log rows")],
		trend.map((m) => [
			m.label,
			format_money(m.added, currency),
			m.removed ? `−${format_money(-m.removed, currency)}` : format_money(0, currency),
			signed_money(m.added + m.removed, currency),
			format_count(m.count),
		])
	);
	const any = trend.some((m) => m.count);
	return section({
		title: __("Budget changes per month"),
		caption: __("Last 12 months: {0} added, {1} removed. Transfers add on one node and remove on another.", [
			format_money(added, currency),
			format_money(-removed, currency),
		]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: any ? chart_with_table(chart, table) : null,
	});
}

function render_change_chart(trend, currency) {
	const up = Math.max(0, ...trend.map((m) => m.added));
	const down = Math.max(0, ...trend.map((m) => -m.removed));
	if (!up && !down) {
		return el("p", { class: "ov-empty", text: __("No budget changes in the last 12 months.") });
	}
	const scale = nice_scale(Math.max(up, down));
	const top = up ? Math.ceil(up / scale.step) * scale.step : 0;
	const bottom = down ? Math.ceil(down / scale.step) * scale.step : 0;
	const span = top + bottom;
	const zero = (top / span) * 100; // % from the top where the baseline sits

	const figure = el("figure", { class: "ov-chart ov-change-chart", style: `--ov-count: ${trend.length}` });
	figure.append(
		el(
			"div",
			{ class: "ov-change-legend", "aria-hidden": "true" },
			el("span", { class: "ov-change-key is-added" }, __("Added")),
			el("span", { class: "ov-change-key is-removed" }, __("Removed"))
		)
	);
	const plot = el("div", { class: "ov-plot" });
	for (let value = -bottom; value <= top; value += scale.step) {
		plot.append(
			el(
				"div",
				{ class: value ? "ov-gridline" : "ov-gridline is-base", style: `top: ${((top - value) / span) * 100}%` },
				el("span", { class: "ov-tick", text: value < 0 ? `−${format_tick(-value)}` : format_tick(value) })
			)
		);
	}
	const columns = el("div", { class: "ov-columns" });
	trend.forEach((m) => {
		const column = el("div", {
			class: "ov-col ov-change-col",
			tabindex: "0",
			role: "img",
			"aria-label": __("{0}: {1} added, {2} removed", [m.label, format_money(m.added, currency), format_money(-m.removed, currency)]),
		});
		const add_bar = el("div", {
			class: m.added ? "ov-change-bar is-added" : "ov-change-bar is-added is-zero",
			style: `bottom: ${100 - zero}%; height: ${top ? (m.added / span) * 100 : 0}%`,
		});
		const remove_bar = el("div", {
			class: "ov-change-bar is-removed",
			style: `top: ${zero}%; height: ${bottom ? (-m.removed / span) * 100 : 0}%`,
		});
		column.append(add_bar, remove_bar);
		attach_tooltip(
			figure,
			column,
			m.added ? add_bar : remove_bar,
			signed_money(m.added + m.removed, currency),
			`${m.label} · ${__("{0} added, {1} removed", [format_money(m.added, currency), format_money(-m.removed, currency)])}`
		);
		columns.append(column);
	});
	plot.append(columns);
	figure.append(
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
	api: "a3_constructa.api.wbs_cost_structure_overview.get_overview",
	storage_key: "a3_constructa.wbs_cost_structure.tab",
	labels: { overview: __("WBS & Cost Structure Overview"), menu: __("WBS & Cost Structure") },
	intro: __("How the approved budget is broken down and placed on the works, and how it has changed."),
	render,
});
