// Asset & Equipment Overview: tab 1 of the Asset & Equipment workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Asset & Equipment Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	const { register, currency } = data;
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Overdue maintenance, unreturned tools and idle equipment"),
				body: render_health(data.health),
			}),
			section({
				title: __("Coming up"),
				caption: __("Maintenance, tool returns, warranties and insurance, soonest first"),
				body: render_coming_up(data.coming_up),
			})
		),
		section({
			title: __("The equipment register"),
			caption: __("Every submitted asset not sold, scrapped or capitalised. Open a row to see those assets."),
			body: el("div", { class: "ov-breakdowns" }, register_breakdowns(register, currency).map(render_breakdown)),
		}),
		render_depreciation_section(data.depreciation, currency),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Repair cost"),
				caption: __("Repairs and the spares they used, last 12 months"),
				body: render_breakdown(repairs_by_asset(data.repairs, currency)),
			}),
			section({
				title: __("Small tools with staff"),
				caption: __("Tool issues with tools not yet returned"),
				body: render_breakdown(tools_by_project(data.tools, currency)),
			})
		),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency. Book value is cost less the depreciation booked so far. Counts follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { depreciation, repairs, maintenance, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_register(data.register, data.tools, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Depreciation, last 12 months"),
				depreciation.restricted ? "—" : format_money(depreciation.booked_year, currency),
				note(
					depreciation.restricted
						? __("You do not have access to depreciation schedules")
						: depreciation.next_date
						? __("Next {0} on {1}", [format_money(depreciation.next_amount, currency), format_date(depreciation.next_date)])
						: __("Nothing scheduled")
				)
			),
			kpi(
				__("Repairs, last 12 months"),
				repairs.restricted ? "—" : format_money(repairs.cost, currency),
				note(repairs.restricted ? __("You do not have access to asset repairs") : repair_note(repairs))
			),
			kpi(
				__("Maintenance due in 30 days"),
				maintenance.restricted ? "—" : format_count(maintenance.due_soon),
				maintenance.restricted
					? note(__("You do not have access to maintenance logs"))
					: maintenance.overdue
					? note(
							maintenance.overdue === 1
								? __("1 task is overdue")
								: __("{0} tasks are overdue", [format_count(maintenance.overdue)]),
							icon("warning", "is-warning")
					  )
					: note(maintenance.open ? __("None overdue") : __("No maintenance planned"))
			),
			health_kpi(data.health)
		)
	);
}

function repair_note(repairs) {
	if (!repairs.count) {
		return repairs.open ? __("{0} open from earlier", [format_count(repairs.open)]) : __("No repairs logged");
	}
	const logged = repairs.count === 1 ? __("1 repair") : __("{0} repairs", [format_count(repairs.count)]);
	const open = !repairs.open ? __("none open") : __("{0} open now", [format_count(repairs.open)]);
	return `${logged} · ${open}`;
}

function render_register(register, tools, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Asset register") }));
	if (register.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to assets.") }));
	} else {
		card.append(
			el(
				"p",
				{ class: "ov-hero-figure" },
				el("span", { class: "ov-hero-value", text: format_count(register.count) }),
				el("span", {
					class: "ov-hero-of",
					text: register.count === 1 ? __("asset on the register") : __("assets on the register"),
				})
			)
		);
		if (register.count) {
			const kept = register.cost ? Math.min(100, Math.max(0, (register.book_value / register.cost) * 100)) : 0;
			card.append(
				el(
					"div",
					{
						class: "ov-meter",
						role: "img",
						"aria-label": __("Book value is {0}% of cost", [Math.round(kept)]),
					},
					el("div", { class: "ov-meter-fill", style: `width: ${kept}%` })
				),
				el("p", {
					class: "ov-hero-caption",
					text: __("{0} book value of {1} at cost", [
						format_money(register.book_value, currency),
						format_money(register.cost, currency),
					]),
				})
			);
		} else {
			card.append(el("p", { class: "ov-hero-caption", text: __("No assets have been submitted yet.") }));
		}
		const issues = [
			register.out_of_order === 1
				? __("1 is out of order")
				: register.out_of_order
				? __("{0} are out of order", [format_count(register.out_of_order)])
				: null,
			register.in_maintenance === 1
				? __("1 is in maintenance")
				: register.in_maintenance
				? __("{0} are in maintenance", [format_count(register.in_maintenance)])
				: null,
		];
		for (const text of issues.filter(Boolean)) {
			card.append(el("p", { class: "ov-hero-issue" }, icon("warning", "is-warning"), el("span", { text })));
		}
	}
	card.append(render_tools_out(tools, currency));
	return card;
}

function render_tools_out(tools, currency) {
	const block = el(
		"div",
		{ class: "ov-hero-sub" },
		el("p", { class: "ov-label", text: __("Small tools with staff") })
	);
	if (tools.restricted) {
		block.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to tool issues.") }));
		return block;
	}
	if (!tools.qty) {
		block.append(el("p", { class: "ov-hero-caption", text: __("No small tools are out with staff.") }));
		return block;
	}
	const people = tools.people === 1 ? __("1 person") : __("{0} people", [format_count(tools.people)]);
	block.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-sub-value", text: format_qty(tools.qty) }),
			el("span", {
				class: "ov-hero-of",
				text: tools.qty === 1 ? __("tool, worth {0}", [format_money(tools.value, currency)]) : __("tools, worth {0}", [format_money(tools.value, currency)]),
			})
		),
		el("p", {
			class: "ov-hero-caption",
			text: tools.late
				? __("With {0} · {1} past the return date", [
						people,
						tools.late === 1 ? __("1 issue") : __("{0} issues", [format_count(tools.late)]),
				  ])
				: __("With {0} · none past the return date", [people]),
		})
	);
	return block;
}

// ---------- Coming up ----------

const KINDS = {
	maintenance: () => __("Maintenance"),
	tool_return: () => __("Tool return"),
	warranty: () => __("Warranty"),
	insurance: () => __("Insurance"),
};

function render_coming_up(coming) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (coming.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to assets, maintenance or tool issues.") }));
		return card;
	}
	if (!coming.rows.length) {
		card.append(el("p", { class: "ov-empty", text: __("No maintenance, tool returns or warranty dates ahead.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			coming.rows.map((row) => {
				const detail =
					row.kind === "tool_return"
						? row.qty === 1
							? __("1 tool")
							: __("{0} tools", [format_qty(row.qty)])
						: row.detail;
				const ends = row.kind === "warranty" || row.kind === "insurance";
				return el(
					"li",
					{},
					form_link(
						row.doctype,
						row.name,
						[
							row_text(row.title, [KINDS[row.kind](), detail, row.name].filter(Boolean).join(" · ")),
							el("span", {
								class: row.late ? "ov-row-when is-late" : "ov-row-when",
								text: ends
									? __("ends {0}", [format_date(row.date)])
									: __("due {0}", [format_date(row.date)]),
							}),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row" }
					)
				);
			})
		)
	);
	return card;
}

// ---------- Breakdowns ----------

function register_breakdowns(register, currency) {
	const by = (title, field, key, measure = "count") => ({
		title,
		doctype: "Asset",
		field,
		filters: register.filters,
		restricted: register.restricted,
		measure,
		currency,
		rows: register.restricted ? [] : register[key],
		total: register.restricted ? 0 : measure === "amount" ? register.book_value : register.count,
	});
	return [
		by(__("By status"), "status", "by_status"),
		by(__("Book value by category"), "asset_category", "by_category", "amount"),
		by(__("By location"), "location", "by_location"),
		by(__("By project"), "project", "by_project"),
	];
}

function repairs_by_asset(repairs, currency) {
	return {
		title: __("By asset"),
		doctype: "Asset Repair",
		field: "asset",
		filters: repairs.filters,
		restricted: repairs.restricted,
		measure: "amount",
		currency,
		rows: repairs.restricted ? [] : repairs.by_asset,
		total: repairs.restricted ? 0 : repairs.cost,
	};
}

function tools_by_project(tools, currency) {
	return {
		title: __("By project"),
		doctype: "Tool Issue",
		field: "project",
		filters: tools.filters,
		restricted: tools.restricted,
		currency,
		rows: tools.restricted ? [] : tools.by_project,
		total: tools.restricted ? 0 : tools.issues,
	};
}

// ---------- Depreciation per month ----------

function render_depreciation_section(depreciation, currency) {
	if (depreciation.restricted) {
		return section({
			title: __("Depreciation by month"),
			caption: __("Booked for the last six months and scheduled for the next six"),
			body: el(
				"div",
				{ class: "ov-card ov-chart-card" },
				el("p", { class: "ov-empty", text: __("You do not have access to Asset Depreciation Schedule") })
			),
		});
	}
	const trend = depreciation.trend;
	const chart = render_depreciation_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("Booked"), __("Scheduled")],
		trend.map((point) => [
			point.label,
			point.booked ? format_money(point.booked, currency) : "—",
			point.scheduled ? format_money(point.scheduled, currency) : "—",
		])
	);
	const any = trend.some((point) => point.booked || point.scheduled);
	return section({
		title: __("Depreciation by month"),
		caption: __("Booked for the last six months and scheduled for the next six, in {0}", [currency]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: any ? chart_with_table(chart, table) : null,
	});
}

function render_depreciation_chart(trend, currency) {
	const total = (point) => point.booked + point.scheduled;
	const max = Math.max(0, ...trend.map(total));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No depreciation is booked or scheduled for these months.") });
	}

	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${trend.length}` });
	figure.append(
		el(
			"div",
			{ class: "ov-legend ov-chart-legend" },
			el("span", {}, el("span", { class: "ov-swatch is-booked" }), el("span", { text: __("Booked") })),
			el("span", {}, el("span", { class: "ov-swatch is-scheduled" }), el("span", { text: __("Scheduled") }))
		)
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

	// Label only the peak month; the tooltip and the table carry the rest.
	const peak = trend.reduce((best, point, index) => (total(point) > total(trend[best]) ? index : best), 0);
	const columns = el("div", { class: "ov-columns" });

	trend.forEach((point, index) => {
		const sum = total(point);
		const bar = el("div", {
			class: sum ? "ov-col-bar" : "ov-col-bar is-zero",
			style: `height: ${(sum / top) * 100}%`,
		});
		if (sum) {
			// Scheduled sits on top of booked, each its share of the column.
			if (point.scheduled) {
				bar.append(el("span", { class: "ov-col-part is-scheduled", style: `flex-grow: ${point.scheduled}` }));
			}
			if (point.booked) {
				bar.append(el("span", { class: "ov-col-part is-booked", style: `flex-grow: ${point.booked}` }));
			}
		}
		if (sum && index === peak) {
			bar.append(el("span", { class: "ov-col-cap", text: format_tick(Math.round(sum)) }));
		}
		const column = el(
			"div",
			{ class: "ov-col", tabindex: "0", role: "img", "aria-label": depreciation_label(point, currency) },
			bar
		);
		attach_tooltip(figure, column, bar, format_money(sum, currency), depreciation_tip(point, currency));
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

function depreciation_label(point, currency) {
	if (point.booked && point.scheduled) {
		return __("{0}: {1} booked, {2} scheduled", [
			point.label,
			format_money(point.booked, currency),
			format_money(point.scheduled, currency),
		]);
	}
	if (point.booked) return __("{0}: {1} booked", [point.label, format_money(point.booked, currency)]);
	if (point.scheduled) return __("{0}: {1} scheduled", [point.label, format_money(point.scheduled, currency)]);
	return __("{0}: none", [point.label]);
}

// The tooltip leads with the month's total, so its label only names the parts.
function depreciation_tip(point, currency) {
	if (point.booked && point.scheduled) return depreciation_label(point, currency);
	if (point.booked) return __("{0}, booked", [point.label]);
	if (point.scheduled) return __("{0}, scheduled", [point.label]);
	return __("{0}, none", [point.label]);
}

mount_overview({
	api: "a3_constructa.api.asset_equipment_overview.get_overview",
	storage_key: "a3_constructa.asset_equipment.tab",
	labels: { overview: __("Asset & Equipment Overview"), menu: __("Asset & Equipment") },
	intro: __("Equipment, maintenance, small tools and depreciation across A3 Constructa."),
	render,
});
