// HR & Time Overview: tab 1 of the HR & Time workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "HR & Time Overview" Custom HTML Block on every `bench migrate`
// (a3_constructa/setup/custom_html_blocks.py). Edit them here, not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.
// Pay is only ever shown as totals: no figure here belongs to one person.

function render(data) {
	const { expenses, currency } = data;
	return [
		render_summary(data),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Approvals, open advances and payroll gaps"),
				body: render_health(data.health),
			}),
			section({
				title: __("Awaiting approval"),
				caption: __("Leave and expense claims waiting for a decision"),
				body: render_awaiting(data.awaiting),
			})
		),
		section({
			title: __("Workforce"),
			caption: __("Active employees. Open a row to see them."),
			body: el("div", { class: "ov-breakdowns" }, workforce(data.workforce).map(breakdown_card)),
		}),
		section({
			title: __("Time and attendance this month"),
			caption: __("Since {0}. Open a row to see the records.", [format_date(data.month_start)]),
			body: el("div", { class: "ov-breakdowns" }, time_and_attendance(data).map(breakdown_card)),
		}),
		render_payroll_trend(data.payroll, currency),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Where expenses went"),
				caption: __("Claimed over the last 12 months, rejected claims left out"),
				body: breakdown_card(expense_projects(expenses, currency)),
			}),
			section({
				title: __("What was claimed"),
				caption: __("The same claims, by the type of each expense line"),
				body: breakdown_card(expense_types(expenses, currency)),
			})
		),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency. Pay is shown as totals only, never per person. Counts follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	return el(
		"div",
		{ class: "ov-summary" },
		render_workforce(data.workforce, data.today),
		el(
			"div",
			{ class: "ov-kpis" },
			payroll_kpi(data.payroll, data.currency),
			expenses_kpi(data.expenses, data.currency),
			timesheets_kpi(data.timesheets),
			health_kpi(data.health)
		)
	);
}

function render_workforce(workforce, today) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Workforce") }));
	if (workforce.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to employees.") }));
	} else {
		card.append(
			el(
				"p",
				{ class: "ov-hero-figure" },
				el("span", { class: "ov-hero-value", text: format_count(workforce.active) }),
				el("span", {
					class: "ov-hero-of",
					text: workforce.active === 1 ? __("active employee") : __("active employees"),
				})
			),
			el("p", {
				class: "ov-hero-caption",
				text:
					workforce.joined || workforce.left
						? __("{0} joined · {1} left in the last 12 months", [workforce.joined, workforce.left])
						: __("No one joined or left in the last 12 months"),
			})
		);
	}
	card.append(render_today(today));
	return card;
}

// Who is in, out and away today. Each figure but check-ins opens its records;
// check-ins count people, and their list holds punches.
function render_today(today) {
	const cells = [
		[__("Present"), today.present],
		[__("Absent"), today.absent],
		[__("On leave"), today.on_leave],
		[__("Checked in"), today.checked_in],
	];
	const readable = cells.filter(([, cell]) => !cell.restricted);
	const caption = !readable.length
		? __("You do not have access to attendance or check-ins.")
		: readable.every(([, cell]) => !cell.count)
		? __("No attendance or check-ins recorded yet today.")
		: null;
	return el(
		"div",
		{ class: "ov-today" },
		el("p", { class: "ov-label", text: __("Today") }),
		el(
			"div",
			{ class: "ov-today-cells" },
			cells.map(([label, cell]) => {
				const content = [
					el("span", { class: "ov-today-value", text: cell.restricted ? "—" : format_count(cell.count) }),
					el("span", { class: "ov-today-label", text: label }),
				];
				const attrs = {
					class: cell.restricted || !cell.count ? "ov-today-cell is-zero" : "ov-today-cell",
					title: cell.restricted ? __("You do not have access to {0}", [__(cell.doctype)]) : null,
				};
				return cell.filters && !cell.restricted
					? list_link(cell.doctype, cell.filters, content, attrs)
					: el("div", attrs, content);
			})
		),
		caption ? el("p", { class: "ov-hero-caption", text: caption }) : null
	);
}

function payroll_kpi(payroll, currency) {
	const label = __("Payroll, last run");
	if (payroll.restricted) return kpi(label, "—", note(__("You do not have access to salary slips")));
	const run = payroll.last_run;
	if (!run) return kpi(label, "—", note(__("No payroll has been run yet")));
	return kpi(
		label,
		format_money(run.amount, currency),
		note(
			run.count === 1
				? __("Gross pay, 1 payslip, {0}", [period_text(run.start, run.end)])
				: __("Gross pay, {0} payslips, {1}", [format_count(run.count), period_text(run.start, run.end)])
		)
	);
}

function expenses_kpi(expenses, currency) {
	const label = __("Expenses, last 30 days");
	if (expenses.restricted) return kpi(label, "—", note(__("You do not have access to expense claims")));
	if (!expenses.count_30d) return kpi(label, format_money(0, currency), note(__("No claims in the last 30 days")));
	const claims = expenses.count_30d === 1 ? __("1 claim") : __("{0} claims", [format_count(expenses.count_30d)]);
	return kpi(
		label,
		format_money(expenses.amount_30d, currency),
		note(
			expenses.waiting_30d
				? __("{0} · {1} awaiting approval", [claims, format_count(expenses.waiting_30d)])
				: claims
		)
	);
}

function timesheets_kpi(timesheets) {
	const label = __("Timesheet hours, this month");
	if (timesheets.restricted) return kpi(label, "—", note(__("You do not have access to timesheets")));
	if (!timesheets.count) return kpi(label, "0", note(__("No timesheets this month")));
	const sheets = timesheets.count === 1 ? __("1 timesheet") : __("{0} timesheets", [format_count(timesheets.count)]);
	const projects = !timesheets.projects
		? __("no project set")
		: timesheets.projects === 1
		? __("1 project")
		: __("{0} projects", [timesheets.projects]);
	return kpi(label, format_hours(timesheets.hours), note(`${sheets} · ${projects}`));
}

// ---------- Lists ----------

function render_awaiting(awaiting) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (awaiting.restricted) {
		card.append(
			el("p", { class: "ov-empty", text: __("You do not have access to leave applications or expense claims.") })
		);
		return card;
	}
	if (!awaiting.rows.length) {
		card.append(el("p", { class: "ov-empty", text: __("Nothing is waiting for approval.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			awaiting.rows.map((row) => {
				const leave = row.doctype === "Leave Application";
				const meta = leave
					? [__("Leave"), __(row.leave_type), days_text(row.days)]
					: [__("Expense claim"), row.project || row.name];
				return el(
					"li",
					{},
					form_link(
						row.doctype,
						row.name,
						[
							row_text(row.employee_name, meta.join(" · ")),
							el("span", {
								class: row.late ? "ov-row-when is-late" : "ov-row-when",
								text: leave
									? __("from {0}", [format_date(row.date)])
									: __("claimed {0}", [format_date(row.date)]),
							}),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row" }
					)
				);
			})
		)
	);
	const more = awaiting.total - awaiting.rows.length;
	if (more > 0) {
		card.append(
			el("p", {
				class: "ov-list-more",
				text: more === 1 ? __("1 more is waiting") : __("{0} more are waiting", [format_count(more)]),
			})
		);
	}
	return card;
}

// ---------- Breakdowns ----------

// The shared bar list, with an empty state that names what is missing.
function breakdown_card(breakdown) {
	const card = render_breakdown(breakdown);
	const empty = card.querySelector(".ov-empty");
	if (empty && !breakdown.restricted && breakdown.empty) empty.textContent = breakdown.empty;
	return card;
}

function by(source, { title, doctype, field, rows, filters, empty, currency = null, measure = "count" }) {
	const restricted = Boolean(source.restricted);
	rows = restricted ? [] : rows || [];
	return {
		title,
		doctype,
		field,
		filters,
		restricted,
		rows,
		empty,
		currency,
		measure,
		total: rows.reduce((sum, row) => sum + (measure === "amount" ? row.amount : row.count), 0),
	};
}

function workforce(workforce) {
	return [
		by(workforce, {
			title: __("By department"),
			doctype: "Employee",
			field: "department",
			rows: workforce.by_department,
			filters: workforce.filters,
			empty: __("No active employees yet."),
		}),
		by(workforce, {
			title: __("By designation"),
			doctype: "Employee",
			field: "designation",
			rows: workforce.by_designation,
			filters: workforce.filters,
			empty: __("No active employees yet."),
		}),
	];
}

function time_and_attendance({ attendance, leave, timesheets, currency }) {
	return [
		by(attendance, {
			title: __("Attendance by status"),
			doctype: "Attendance",
			field: "status",
			rows: attendance.by_status,
			filters: attendance.filters,
			empty: __("No attendance marked this month."),
		}),
		by(attendance, {
			title: __("Days attended by project"),
			doctype: "Attendance",
			field: "project",
			rows: attendance.by_project,
			filters: attendance.attended_filters,
			empty: __("No one marked present this month."),
		}),
		by(leave, {
			title: __("Approved leave by type"),
			doctype: "Leave Application",
			field: "leave_type",
			rows: leave.by_type,
			filters: leave.filters,
			empty: __("No approved leave this month."),
		}),
		by(timesheets, {
			title: __("Timesheets by project"),
			doctype: "Timesheet",
			field: "project",
			rows: timesheets.by_project,
			filters: timesheets.filters,
			currency,
			empty: __("No timesheets this month."),
		}),
	];
}

function expense_projects(expenses, currency) {
	return by(expenses, {
		title: __("By project"),
		doctype: "Expense Claim",
		field: "project",
		rows: expenses.by_project,
		filters: expenses.year_filters,
		currency,
		measure: "amount",
		empty: __("No expense claims in the last 12 months."),
	});
}

function expense_types(expenses, currency) {
	return by(expenses, {
		title: __("By expense type"),
		doctype: "Expense Claim",
		field: "expense_type",
		rows: expenses.by_type,
		filters: expenses.year_filters,
		currency,
		measure: "amount",
		empty: __("No expense claims in the last 12 months."),
	});
}

// ---------- Payroll cost per month ----------

function render_payroll_trend(payroll, currency) {
	const title = __("Payroll cost per month");
	if (payroll.restricted) {
		return section({
			title,
			body: el(
				"div",
				{ class: "ov-card ov-chart-card" },
				el("p", { class: "ov-empty", text: __("You do not have access to salary slips.") })
			),
		});
	}

	const trend = payroll.trend.map((point) => {
		const month = moment(`${point.month}-01`);
		return { ...point, label: month.format("MMM YYYY"), short: month.format("MMM") };
	});
	const total = trend.reduce((sum, point) => sum + point.amount, 0);
	const chart = render_trend_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("Payslips"), __("Gross pay")],
		trend.map((point) => [point.label, format_count(point.count), format_money(point.amount, currency)])
	);
	// With nothing to tabulate there is no table to swap to.
	const toggle = total ? chart_with_table(chart, table) : null;
	table.hidden = true;

	return section({
		title,
		caption: total
			? __("Gross pay of submitted payslips: {0} over the last 12 months", [format_money(total, currency)])
			: __("Gross pay of submitted payslips over the last 12 months"),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: toggle,
	});
}

function render_trend_chart(trend, currency) {
	const max = Math.max(0, ...trend.map((point) => point.amount));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No payroll has been run in the last 12 months.") });
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
	const peak = trend.reduce((best, point, index) => (point.amount > trend[best].amount ? index : best), 0);
	const latest = trend.length - 1;
	const columns = el("div", { class: "ov-columns" });

	trend.forEach((point, index) => {
		const bar = el("div", {
			class: point.amount ? "ov-col-bar" : "ov-col-bar is-zero",
			style: `height: ${(point.amount / top) * 100}%`,
		});
		if (point.amount && (index === peak || index === latest)) {
			bar.append(el("span", { class: "ov-col-cap", text: format_money_short(point.amount, currency) }));
		}
		const column = el(
			"div",
			{
				class: "ov-col",
				tabindex: "0",
				role: "img",
				"aria-label": __("{0}: {1} gross pay", [point.label, format_money(point.amount, currency)]),
			},
			bar
		);
		const slips = point.count === 1 ? __("1 payslip") : __("{0} payslips", [format_count(point.count)]);
		attach_tooltip(figure, column, bar, format_money(point.amount, currency), `${point.label} · ${slips}`);
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

// ---------- Formatting ----------

function format_hours(value) {
	return format_number(value, null, Number.isInteger(flt(value, 1)) ? 0 : 1);
}

function days_text(days) {
	return days === 1 ? __("1 day") : __("{0} days", [format_hours(days)]);
}

// "$ 75K" over a column, where a full amount would not fit; the symbol sits
// as format_money places it.
function format_money_short(value, currency) {
	const symbol = typeof get_currency_symbol === "function" ? get_currency_symbol(currency) : currency;
	return symbol ? `${symbol}\u00a0${format_tick(value)}` : format_tick(value);
}

// "Sep 2026" for a whole calendar month, else the two dates.
function period_text(start, end) {
	const from = moment(start);
	const to = moment(end);
	if (from.date() === 1 && to.isSame(from.clone().endOf("month"), "day")) return from.format("MMM YYYY");
	return `${from.format("D MMM")} – ${format_date(end)}`;
}

mount_overview({
	api: "a3_constructa.api.hr_time_overview.get_overview",
	storage_key: "a3_constructa.hr_time.tab",
	labels: { overview: __("HR & Time Overview"), menu: __("HR & Time") },
	intro: __("People, attendance, leave, payroll, expenses and timesheets across A3 Constructa."),
	render,
});
