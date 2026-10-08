// Planning & Budgeting Overview: tab 1 of the Planning & Budgeting workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Planning & Budgeting Overview" Custom HTML Block on every
// `bench migrate` (a3_constructa/setup/custom_html_blocks.py). Edit them here,
// not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	return [
		render_summary(data),
		render_timeline_section(data.awards),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Budget and planning steps still to do, and requests the programme needs"),
				body: render_health(data.health),
			}),
			render_plan_due_section(data.plan)
		),
		section({
			title: __("Budget allocated to WBS"),
			caption: __("Approved BOQ budget by project, and how much of it has been split across the works"),
			body: render_budget(data.budget, data.currency),
		}),
		section({
			title: __("Procurement plan"),
			caption: __("Lines on open plans. Most follow the programme: wanted on site before their task starts, requested a lead time before that."),
			body: el("div", { class: "ov-breakdowns" }, plan_breakdowns(data.plan).map(render_breakdown)),
		}),
		section({
			title: __("Pipeline"),
			caption: __("Where every record stands. Open a row to see those records."),
			body: el("div", { class: "ov-breakdowns" }, pipeline(data).map(render_breakdown)),
		}),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency. Awards and variations priced in another currency are left out of the totals. Milestones, deliverables and the order book are on Contracts & Awards. Counts follow your permissions.",
				[data.currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { plan, variations, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_budget_hero(data.budget, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Plan lines"),
				plan.restricted ? "—" : format_count(plan.lines),
				note(
					plan.restricted
						? __("You do not have access to procurement plans")
						: __("{0} from the programme · {1} typed in", [plan.from_schedule, plan.by_hand])
				)
			),
			kpi(
				__("Requests due in {0} days", [plan.restricted ? 14 : plan.window_days]),
				plan.restricted ? "—" : format_count(plan.due_soon),
				note(
					plan.restricted
						? __("You do not have access to procurement plans")
						: plan.overdue
						? __("{0} more already past their PR date", [plan.overdue])
						: __("None past their PR date")
				)
			),
			kpi(
				__("Approved variations"),
				variations.restricted ? "—" : format_money(variations.approved_value, currency),
				note(variations_note(variations, currency))
			),
			health_kpi(data.health)
		)
	);
}

function render_budget_hero(budget, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Approved BOQ budget") }));
	if (budget.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to BOQs.") }));
		return card;
	}

	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value ov-hero-money", text: format_money(budget.approved_budget, currency) })
		),
		el("p", {
			class: "ov-hero-caption",
			text: __("{0} approved · {1} awaiting approval", [budget.approved_count, budget.pending_count]),
		})
	);

	if (!budget.approved_budget) {
		card.append(
			el(
				"p",
				{ class: "ov-hero-caption" },
				list_link("BOQ", {}, __("Approve the first BOQ"), { class: "ov-text-link" })
			)
		);
		return card;
	}

	if (!budget.allocation_restricted) {
		const ratio = budget.allocated / budget.approved_budget;
		const percent = Math.round(ratio * 100);
		card.append(
			el(
				"div",
				{ class: "ov-hero-progress" },
				el(
					"div",
					{ class: "ov-meter-head" },
					el("span", { text: __("Allocated to WBS") }),
					el("strong", { text: `${percent}%` })
				),
				el(
					"div",
					{
						class: "ov-meter",
						role: "meter",
						"aria-label": __("Allocated to WBS"),
						"aria-valuemin": 0,
						"aria-valuemax": 100,
						"aria-valuenow": percent,
					},
					el("div", { class: "ov-meter-fill", style: `width: ${Math.min(100, ratio * 100)}%` })
				)
			),
			el(
				"dl",
				{ class: "ov-hero-split" },
				el("dt", { text: __("On the works") }),
				el("dd", { text: format_money(budget.allocated, currency) }),
				el("dt", { text: __("Still to allocate") }),
				el("dd", { text: format_money(Math.max(0, budget.approved_budget - budget.allocated), currency) })
			)
		);
	} else {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to WBS allocations.") }));
	}
	return card;
}

function variations_note(variations, currency) {
	if (variations.restricted) return __("You do not have access to variation orders");
	if (!variations.pending_count) return __("None pending");
	return variations.pending_count === 1
		? __("1 pending, worth {0}", [signed_money(variations.pending_value, currency)])
		: __("{0} pending, worth {1}", [variations.pending_count, signed_money(variations.pending_value, currency)]);
}

// ---------- Award timeline ----------

function render_timeline_section(awards) {
	const title = __("Award timeline");
	if (awards.restricted || !awards.timeline.length) {
		const text = awards.restricted
			? __("You do not have access to awarded quotations.")
			: __("No active awards yet.");
		return section({ title, body: el("div", { class: "ov-card" }, el("p", { class: "ov-empty", text }), contracts_link()) });
	}

	const rows = awards.timeline;
	const chart = render_timeline_chart(rows);
	const table = render_table(
		[__("Award"), __("Client"), __("Status"), __("Start"), __("Completion"), __("Progress"), __("Value")],
		rows.map((award) => [
			award.title,
			award.customer,
			__(award.status),
			award.start ? format_date(award.start) : "—",
			award.end ? format_date(award.end) : "—",
			`${Math.round(award.progress)}%`,
			format_money(award.value, award.currency),
		])
	);
	let caption = __("Active awards by value, from start to revised completion. The filled part is progress.");
	if (awards.active_count > rows.length) {
		caption += " " + __("Showing the {0} largest of {1}.", [rows.length, awards.active_count]);
	}
	return section({
		title,
		caption,
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table, contracts_link()),
		action: chart_with_table(chart, table),
	});
}

function render_timeline_chart(rows) {
	const today = moment().startOf("day");
	const dated = rows.filter((award) => award.start && award.end);
	let from = moment.min(today, ...dated.map((award) => moment(award.start)));
	let to = moment.max(today, ...dated.map((award) => moment(award.end)));
	// Keep the first and last bars off the edges.
	const pad = Math.max(7, Math.round(to.diff(from, "days") * 0.03));
	from = from.clone().subtract(pad, "days");
	to = to.clone().add(pad, "days");
	const span = Math.max(1, to.diff(from, "days"));
	const x = (date) => (moment(date).diff(from, "days") / span) * 100;

	const figure = el("figure", { class: "ov-timeline" });
	figure.append(
		el(
			"div",
			{ class: "ov-tl-row ov-tl-head", "aria-hidden": "true" },
			el("span", { class: "ov-tl-label" }),
			render_timeline_axis(from, to, today, x),
			el("span", { class: "ov-tl-value", text: __("Value") })
		)
	);

	for (const award of rows) {
		const track = el("div", { class: "ov-tl-track" }, el("span", { class: "ov-tl-today", style: `left: ${x(today)}%` }));
		if (award.start && award.end) {
			const bar = el(
				"div",
				{
					class: "ov-tl-bar",
					style: `left: ${x(award.start)}%; width: ${Math.max(0.5, x(award.end) - x(award.start))}%`,
				},
				el("div", { class: "ov-tl-progress", style: `width: ${Math.min(100, award.progress)}%` })
			);
			track.append(bar);
			track.setAttribute("tabindex", "0");
			track.setAttribute(
				"aria-label",
				__("{0}: {1}% complete, {2} to {3}", [
					award.title,
					Math.round(award.progress),
					format_date(award.start),
					format_date(award.end),
				])
			);
			attach_tooltip(
				figure,
				track,
				bar,
				__("{0}% complete", [Math.round(award.progress)]),
				`${format_date(award.start)} – ${format_date(award.end)}`
			);
		} else {
			track.append(el("span", { class: "ov-tl-nodates", text: __("No start or completion date") }));
		}

		figure.append(
			el(
				"div",
				{ class: "ov-tl-row" },
				render_award_label(award),
				track,
				el(
					"div",
					{ class: "ov-tl-value" },
					el("strong", { text: format_money(award.value, award.currency) }),
					el("span", { text: __("{0}% done", [Math.round(award.progress)]) })
				)
			)
		);
	}
	return figure;
}

// Month ticks along the top, thinned out for long programmes, plus today.
function render_timeline_axis(from, to, today, x) {
	const axis = el("div", { class: "ov-tl-axis" });
	const months = to.diff(from, "months");
	const every = months > 30 ? 6 : months > 14 ? 3 : months > 7 ? 2 : 1;
	const tick = from.clone().startOf("month").add(1, "month");
	const today_at = x(today);
	while (tick.isBefore(to)) {
		// A tick this close to today would sit under the "Today" label.
		if (tick.month() % every === 0 && Math.abs(x(tick) - today_at) > 5) {
			const label = tick.month() === 0 ? tick.format("MMM ’YY") : tick.format("MMM");
			axis.append(el("span", { class: "ov-tl-tick", style: `left: ${x(tick)}%`, text: label }));
		}
		tick.add(1, "month");
	}
	axis.append(el("span", { class: "ov-tl-today-label", style: `left: ${x(today)}%`, text: __("Today") }));
	return axis;
}

function render_award_label(award) {
	let issue = null;
	if (award.days_late > 0) {
		issue = [
			icon("critical", "is-critical"),
			award.days_late === 1
				? __("1 day past completion")
				: __("{0} days past completion", [award.days_late]),
		];
	} else if (award.overdue_milestones) {
		issue = [
			icon("warning", "is-warning"),
			award.overdue_milestones === 1
				? __("1 milestone overdue")
				: __("{0} milestones overdue", [award.overdue_milestones]),
		];
	}
	return form_link(
		"Awarded Quotation",
		award.name,
		[
			el("span", { class: "ov-tl-title", text: award.title, title: award.title }),
			el("span", { class: "ov-tl-meta", text: `${award.customer} · ${__(award.status)}` }),
			issue ? el("span", { class: "ov-tl-meta ov-tl-issue" }, issue[0], el("span", { text: issue[1] })) : null,
		],
		{ class: "ov-tl-label" }
	);
}

// Milestones, deliverables and the order book moved to Contracts & Awards (D-03).
function contracts_link() {
	const href = "/app/contracts-%26-awards";
	const link = el(
		"a",
		{ class: "ov-text-link", href },
		__("Milestones, deliverables and the order book are on Contracts & Awards")
	);
	link.addEventListener("click", (event) => {
		if (!is_plain_click(event)) return;
		event.preventDefault();
		frappe.router.push_state(href);
	});
	return el("p", { class: "ov-contracts-link" }, link);
}

// ---------- Requests the programme needs ----------

function render_plan_due_section(plan) {
	const title = __("Requests due");
	const card = el("div", { class: "ov-card ov-list-card" });
	if (plan.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to procurement plans.") }));
		return section({ title, body: card });
	}

	if (!plan.list.length) {
		const text = plan.lines
			? __("No request is due in the next {0} days.", [plan.window_days])
			: __("No plan lines yet. Use Refresh from schedule on a procurement plan.");
		card.append(el("p", { class: "ov-empty", text }));
	} else {
		card.append(
			el(
				"ul",
				{ class: "ov-rows" },
				plan.list.map((line) =>
					el(
						"li",
						{},
						form_link(
							"Procurement Plan",
							line.plan,
							[
								line.days < 0 ? icon("critical", "is-critical") : icon("empty", "is-muted"),
								row_text(
									line.item,
									[
										format_qty(line.qty, line.uom),
										__(line.route || "Buy"),
										line.on_site ? __("on site {0}", [format_date(line.on_site)]) : null,
									]
										.filter(Boolean)
										.join(" · ")
								),
								el("span", {
									class: line.days < 0 ? "ov-row-when is-late" : "ov-row-when",
									text: due_in(line.days),
								}),
								icon("chevron", "ov-chevron"),
							],
							{ class: "ov-row" }
						)
					)
				)
			)
		);
	}

	return section({
		title,
		caption: __("Purchase requests to raise: {0} past their PR date · {1} due in the next {2} days", [
			plan.overdue,
			plan.due_soon,
			plan.window_days,
		]),
		body: card,
	});
}

function due_in(days) {
	if (days < -1) return __("{0} days late", [-days]);
	if (days === -1) return __("1 day late");
	if (days === 0) return __("Due today");
	if (days === 1) return __("Tomorrow");
	return __("In {0} days", [days]);
}

// ---------- Budget ----------

function render_budget(budget, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (budget.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to BOQs.") }));
		return card;
	}
	if (!budget.projects.length) {
		card.append(
			el("p", {
				class: "ov-empty",
				text: __("No approved BOQs yet. A BOQ's budget counts here once it is approved."),
			})
		);
		return card;
	}

	card.append(
		el(
			"ul",
			{ class: "ov-meters" },
			budget.projects.map((project) => {
				const ratio = project.budget ? project.allocated / project.budget : 0;
				const over = ratio > 1.0005;
				const figure = el(
					"span",
					{ class: "ov-meter-figure" },
					over ? icon("critical", "is-critical") : null,
					el("span", {
						text: __("{0} of {1}", [
							format_money(project.allocated, currency),
							format_money(project.budget, currency),
						]),
					}),
					el("strong", { text: over ? __("Over-allocated") : `${Math.round(ratio * 100)}%` })
				);
				return el(
					"li",
					{},
					list_link(
						"WBS Allocation",
						{ project: project.project },
						[
							el("span", { class: "ov-meter-label", text: project.label, title: project.label }),
							el(
								"span",
								{
									class: "ov-meter",
									role: "meter",
									"aria-label": __("{0}: allocated to WBS", [project.label]),
									"aria-valuemin": 0,
									"aria-valuemax": 100,
									"aria-valuenow": Math.round(ratio * 100),
								},
								el("span", {
									class: over ? "ov-meter-fill is-over" : "ov-meter-fill",
									style: `width: ${Math.min(100, ratio * 100)}%`,
								})
							),
							figure,
						],
						{ class: "ov-meter-row" }
					)
				);
			})
		)
	);
	if (budget.allocation_restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to WBS allocations.") }));
	}
	return card;
}

// ---------- Pipeline ----------

function plan_breakdowns(plan) {
	const lines = (title, rows) => ({
		title,
		doctype: "Procurement Plan",
		field: "name",
		filters: {},
		restricted: plan.restricted,
		rows: plan.restricted ? [] : rows,
		total: plan.restricted ? 0 : plan.lines,
	});
	return [
		lines(__("Plan lines by state"), plan.by_state),
		lines(__("Plan lines by route"), plan.by_route),
	];
}

function pipeline(data) {
	const { budget, plan, currency } = data;
	const by_status = (title, doctype, part, with_money = false) => ({
		title,
		doctype,
		field: "status",
		filters: {},
		restricted: part.restricted,
		currency: with_money ? currency : null,
		rows: part.restricted ? [] : part.by_status,
		total: part.restricted ? 0 : part.by_status.reduce((sum, row) => sum + row.count, 0),
	});
	return [
		by_status(__("BOQs by status"), "BOQ", budget, true),
		by_status(__("Procurement plans by status"), "Procurement Plan", plan),
	];
}

function signed_money(value, currency) {
	return value > 0 ? `+${format_money(value, currency)}` : format_money(value, currency);
}

mount_overview({
	api: "a3_constructa.api.planning_overview.get_overview",
	storage_key: "a3_constructa.planning.tab",
	labels: { overview: __("Planning & Budgeting Overview"), menu: __("Planning & Budgeting") },
	intro: __("Budgets, the award programme and what the programme needs ordered, across A3 Constructa."),
	render,
});
