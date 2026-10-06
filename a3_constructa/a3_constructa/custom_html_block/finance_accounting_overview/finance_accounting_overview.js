// Finance & Accounting Overview: tab 1 of the Finance & Accounting workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Finance & Accounting Overview" Custom HTML Block on every
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
				caption: __("Late money, unbilled goods and unfinished entries"),
				body: render_health(data.health),
			}),
			section({
				title: __("Due and overdue"),
				caption: __("Unpaid invoices, the longest overdue first, then those due in the next 30 days"),
				body: render_due(data.due, currency),
			})
		),
		section({
			title: __("Who owes and who is owed"),
			caption: __("Unpaid submitted invoices. Open a row to see those invoices."),
			body: el("div", { class: "ov-breakdowns" }, ledgers(data, currency).map(render_breakdown)),
		}),
		render_flow(data.flow, currency),
		section({
			title: __("Commitments and budget"),
			caption: __("Orders not yet invoiced either way, retention held back and the budget used"),
			body: render_commitments(data, currency),
		}),
		section({
			title: __("Projects"),
			caption: __("How much of each project's sales orders is billed, and the margin after its recorded costs"),
			body: render_projects(data.projects, currency),
		}),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency; an invoice in another currency is converted at its invoice rate. Figures follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { receivable, payable, profit, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_cash(data.cash, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Owed to us"),
				receivable.restricted ? "—" : format_money(receivable.total, currency),
				owed_note(receivable, currency, __("You do not have access to sales invoices"), __("No unpaid customer invoices"))
			),
			kpi(
				__("We owe suppliers"),
				payable.restricted ? "—" : format_money(payable.total, currency),
				owed_note(payable, currency, __("You do not have access to purchase invoices"), __("No unpaid supplier invoices"))
			),
			kpi(
				__("Profit this fiscal year"),
				profit.restricted || !profit.fiscal_year ? "—" : format_money(profit.net, currency),
				note(
					profit.restricted
						? __("You do not have access to the ledger")
						: !profit.fiscal_year
						? __("No fiscal year covers today")
						: __("{0} income, {1} expenses since {2}", [
								format_money(profit.income, currency),
								format_money(profit.expense, currency),
								format_date(profit.from_date),
						  ])
				)
			),
			health_kpi(data.health)
		)
	);
}

function owed_note(side, currency, restricted_text, empty_text) {
	if (side.restricted) return note(restricted_text);
	if (!side.count) return note(empty_text);
	if (!side.overdue_count) {
		return note(
			side.count === 1
				? __("1 unpaid invoice, none overdue")
				: __("{0} unpaid invoices, none overdue", [side.count])
		);
	}
	const overdue = format_money(side.overdue, currency);
	return note(
		side.overdue_count === 1
			? __("{0} overdue on 1 invoice", [overdue])
			: __("{0} overdue on {1} invoices", [overdue, side.overdue_count]),
		icon("warning", "is-warning")
	);
}

function render_cash(cash, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Cash & bank") }));
	if (cash.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to the ledger.") }));
		return card;
	}
	const counts = [];
	if (cash.bank_count) {
		counts.push(cash.bank_count === 1 ? __("1 bank account") : __("{0} bank accounts", [cash.bank_count]));
	}
	if (cash.cash_count) {
		counts.push(cash.cash_count === 1 ? __("1 cash account") : __("{0} cash accounts", [cash.cash_count]));
	}
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value ov-hero-money", text: format_money(cash.total, currency) })
		),
		el("p", {
			class: "ov-hero-caption",
			text: counts.length
				? [...counts, __("as at {0}", [format_date(cash.as_on)])].join(" · ")
				: __("No bank or cash accounts are set up yet."),
		})
	);
	if (cash.accounts.length) {
		const rows = cash.accounts.map((account) =>
			el(
				"li",
				{},
				list_link(
					"GL Entry",
					{ account: account.name, is_cancelled: 0, posting_date: ["<=", cash.as_on] },
					[
						el("span", { class: "ov-account-name", text: account.label, title: account.name }),
						el("span", { class: "ov-account-type", text: __(account.type) }),
						el("span", { class: "ov-account-balance", text: format_money(account.balance, currency) }),
					],
					{ class: "ov-account" }
				)
			)
		);
		if (cash.other_count) {
			rows.push(
				el(
					"li",
					{},
					el(
						"div",
						{ class: "ov-account" },
						el("span", {
							class: "ov-account-name",
							text:
								cash.other_count === 1
									? __("1 more account")
									: __("{0} more accounts", [cash.other_count]),
						}),
						el("span", { class: "ov-account-type" }),
						el("span", { class: "ov-account-balance", text: format_money(cash.other_balance, currency) })
					)
				)
			);
		}
		card.append(
			el(
				"div",
				{ class: "ov-hero-accounts" },
				el("p", { class: "ov-label", text: __("By account") }),
				el("ul", { class: "ov-accounts" }, rows)
			)
		);
	}
	return card;
}

// ---------- Lists ----------

function render_due(due, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (due.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to invoices.") }));
		return card;
	}
	if (!due.rows.length) {
		card.append(
			el("p", { class: "ov-empty", text: __("No unpaid invoices are overdue or due in the next 30 days.") })
		);
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			due.rows.map((invoice) =>
				el(
					"li",
					{},
					form_link(
						invoice.doctype,
						invoice.name,
						[
							row_text(
								invoice.party,
								[
									invoice.doctype === "Sales Invoice" ? __("Owed to us") : __("We owe"),
									invoice.name,
								].join(" · ")
							),
							el(
								"span",
								{ class: "ov-money-cell" },
								el("strong", { text: format_money(invoice.amount, currency) }),
								el("span", {
									class: invoice.days_late > 0 ? "ov-row-when is-late" : "ov-row-when",
									text: due_text(invoice),
								})
							),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row" }
					)
				)
			)
		)
	);
	if (due.more) {
		card.append(
			el("p", {
				class: "ov-list-more",
				text: due.more === 1 ? __("and 1 more invoice") : __("and {0} more invoices", [due.more]),
			})
		);
	}
	return card;
}

function due_text(invoice) {
	if (invoice.days_late > 0) {
		return invoice.days_late === 1
			? __("1 day overdue")
			: __("{0} days overdue", [invoice.days_late]);
	}
	if (invoice.days_late === 0) return __("due today");
	return __("due {0}", [format_date(invoice.due_date)]);
}

function render_projects(projects, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (projects.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to projects.") }));
		return card;
	}
	if (!projects.rows.length) {
		card.append(el("p", { class: "ov-empty", text: __("No projects yet.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			projects.rows.map((project) => {
				const billed = format_money(project.billed, currency);
				const share = project.ordered ? Math.round((project.billed / project.ordered) * 100) : null;
				return el(
					"li",
					{},
					form_link(
						"Project",
						project.name,
						[
							row_text(
								project.title,
								[__(project.status), __("costs {0}", [format_money(project.cost, currency)])].join(" · ")
							),
							el(
								"span",
								{ class: "ov-progress-cell" },
								share === null
									? null
									: el(
											"span",
											{
												class: "ov-meter",
												role: "img",
												"aria-label": __("{0}% of sales orders billed", [share]),
											},
											el("span", { class: "ov-meter-fill", style: `width: ${Math.min(share, 100)}%` })
									  ),
								el("span", {
									class: "ov-row-meta",
									text:
										share === null
											? project.billed
												? __("{0} billed, no sales order", [billed])
												: __("No sales order or billing yet")
											: __("{0} of {1} billed ({2}%)", [
													billed,
													format_money(project.ordered, currency),
													share,
											  ]),
								})
							),
							el(
								"span",
								{ class: "ov-money-cell" },
								el("strong", { text: format_money(project.margin, currency) }),
								el("span", {
									text: project.billed
										? __("{0}% margin", [format_number(project.margin_percent, null, 1)])
										: __("before billing"),
								})
							),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row ov-progress-row" }
					)
				);
			})
		)
	);
	if (projects.count > projects.rows.length) {
		const more = projects.count - projects.rows.length;
		card.append(
			el("p", {
				class: "ov-list-more",
				text: more === 1 ? __("and 1 more project") : __("and {0} more projects", [more]),
			})
		);
	}
	return card;
}

// ---------- Commitments ----------

function render_commitments(data, currency) {
	const { committed, order_book, retention } = data.commitments;
	const { budget } = data;
	const tiles = el(
		"div",
		{ class: "ov-kpis" },
		kpi(
			__("Committed but unbilled"),
			committed.restricted ? "—" : format_money(committed.amount, currency),
			note(
				committed.restricted
					? __("You do not have access to purchase orders")
					: !committed.count
					? __("No open purchase orders")
					: committed.count === 1
					? __("On 1 open purchase order")
					: __("On {0} open purchase orders", [committed.count])
			)
		),
		kpi(
			__("Sales orders to bill"),
			order_book.restricted ? "—" : format_money(order_book.amount, currency),
			note(
				order_book.restricted
					? __("You do not have access to sales orders")
					: !order_book.count
					? __("No open sales orders")
					: order_book.count === 1
					? __("On 1 open sales order")
					: __("On {0} open sales orders", [order_book.count])
			)
		),
		kpi(
			__("Retention held"),
			retention.restricted ? "—" : format_money(retention.amount, currency),
			note(
				retention.restricted
					? __("You do not have access to the ledger")
					: !retention.accounts
					? __("No Retention Payable account")
					: retention.amount
					? __("Balance of the Retention Payable account")
					: __("Nothing held back from subcontractors")
			)
		),
		kpi(
			__("Budget used"),
			budget.restricted || budget.percent === null ? "—" : `${format_number(budget.percent, null, 1)}%`,
			note(
				budget.restricted
					? __("You do not have access to the budget")
					: !budget.budget
					? __("No WBS budget allocated yet")
					: __("{0} spent and {1} committed of {2}", [
							format_money(budget.actual, currency),
							format_money(budget.committed, currency),
							format_money(budget.budget, currency),
					  ])
			),
			!budget.restricted && budget.percent > 100 ? icon("warning", "is-warning") : null
		)
	);
	return el("div", { class: "ov-tiles" }, tiles);
}

// ---------- Breakdowns ----------

function ledgers(data, currency) {
	const { receivable, payable } = data;
	const by = (title, side, doctype, field, rows) => ({
		title,
		doctype,
		field,
		filters: side.filters,
		restricted: side.restricted,
		measure: "amount",
		currency,
		// Nothing unpaid: the empty state, not a row of zero bars.
		rows: side.restricted || !side.count ? [] : rows,
		total: side.restricted ? 0 : side.total,
	});
	return [
		by(__("Owed to us, by days overdue"), receivable, "Sales Invoice", "due_date", receivable.ageing),
		by(__("We owe, by days overdue"), payable, "Purchase Invoice", "due_date", payable.ageing),
		by(__("Customers owing the most"), receivable, "Sales Invoice", "customer", receivable.by_party),
		by(__("Suppliers we owe the most"), payable, "Purchase Invoice", "supplier", payable.by_party),
	];
}

// ---------- Cash in and out ----------

function render_flow(flow, currency) {
	const title = __("Cash in and out");
	if (flow.restricted) {
		return section({
			title,
			caption: __("Bank and cash accounts, month by month"),
			body: el(
				"div",
				{ class: "ov-card ov-chart-card" },
				el("p", { class: "ov-empty", text: __("You do not have access to the ledger.") })
			),
		});
	}
	const { trend } = flow;
	const total_in = trend.reduce((sum, point) => sum + point.money_in, 0);
	const total_out = trend.reduce((sum, point) => sum + point.money_out, 0);

	const chart = render_flow_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("In"), __("Out"), __("Net")],
		trend.map((point) => [
			point.label,
			format_money(point.money_in, currency),
			format_money(point.money_out, currency),
			format_money(point.money_in - point.money_out, currency),
		])
	);
	table.classList.add("ov-flow-table");
	const toggle = total_in || total_out ? chart_with_table(chart, table) : null;

	return section({
		title,
		caption: __("Bank and cash accounts, last 12 months: {0} in, {1} out", [
			format_money(total_in, currency),
			format_money(total_out, currency),
		]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: toggle,
	});
}

// Paired columns per month: money in (green) beside money out (navy).
function render_flow_chart(trend, currency) {
	const max = Math.max(0, ...trend.flatMap((point) => [point.money_in, point.money_out]));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("No money moved through bank or cash in the last 12 months.") });
	}

	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${trend.length}` });
	const legend = el(
		"div",
		{ class: "ov-legend ov-chart-legend" },
		el("span", {}, el("span", { class: "ov-swatch is-in" }), el("span", { text: __("Money in") })),
		el("span", {}, el("span", { class: "ov-swatch is-out" }), el("span", { text: __("Money out") }))
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

	// Label only each series' peak; the tooltip and table carry the rest.
	const peak = (key) => trend.reduce((best, point, index) => (point[key] > trend[best][key] ? index : best), 0);
	const peaks = { money_in: peak("money_in"), money_out: peak("money_out") };
	const columns = el("div", { class: "ov-columns" });

	trend.forEach((point, index) => {
		const bar = (key, kind) => {
			const value = point[key];
			const node = el("div", {
				class: value ? `ov-col-bar is-${kind}` : `ov-col-bar is-${kind} is-zero`,
				style: `height: ${(value / top) * 100}%`,
			});
			if (value && index === peaks[key]) {
				node.append(el("span", { class: `ov-col-cap is-${kind}`, text: format_tick(Math.round(value)) }));
			}
			return node;
		};
		const bar_in = bar("money_in", "in");
		const bar_out = bar("money_out", "out");
		const pair = el("div", { class: "ov-col-pair" }, bar_in, bar_out);
		const money_in = format_money(point.money_in, currency);
		const money_out = format_money(point.money_out, currency);
		const column = el(
			"div",
			{
				class: "ov-col",
				tabindex: "0",
				role: "img",
				"aria-label": __("{0}: {1} in, {2} out", [point.label, money_in, money_out]),
			},
			pair
		);
		// The tooltip sits over the taller of the two bars.
		const anchor = point.money_in >= point.money_out ? bar_in : bar_out;
		attach_tooltip(figure, column, anchor, __("{0} in · {1} out", [money_in, money_out]), point.label);
		columns.append(column);
	});

	plot.append(columns);
	figure.append(
		legend,
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
	api: "a3_constructa.api.finance_accounting_overview.get_overview",
	storage_key: "a3_constructa.finance_accounting.tab",
	labels: { overview: __("Finance & Accounting Overview"), menu: __("Finance & Accounting") },
	intro: __("Cash, money owed either way, profit and commitments across A3 Constructa."),
	render,
});
