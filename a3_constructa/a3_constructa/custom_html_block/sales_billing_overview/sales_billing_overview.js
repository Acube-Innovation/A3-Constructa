// Sales & Billing Overview: tab 1 of the Sales & Billing workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Sales & Billing Overview" Custom HTML Block on every
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
				caption: __("Money waiting on a certificate, an invoice or a date"),
				body: render_health(data.health),
			}),
			section({
				title: __("Recent invoices"),
				caption: __("The latest invoices to clients"),
				body: render_recent(data.recent, currency),
			})
		),
		section({
			title: __("Billing and receivables"),
			caption: __("Open a row to see those invoices."),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(award_breakdown(data.billing, currency)),
				render_breakdown(ageing_breakdown(data.receivable, currency))
			),
		}),
		section({
			title: __("Certificates and retention"),
			caption: __("Interim payment certificates by status, and the retention each client still holds"),
			body: el(
				"div",
				{ class: "ov-breakdowns" },
				render_breakdown(ipc_breakdown(data.ipcs)),
				render_breakdown(retention_breakdown(data.retention, currency))
			),
		}),
		render_trend_section(data.trend, currency),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Money is shown in {0}, the company's default currency. Billed amounts are before VAT except in the monthly chart, which compares invoices and receipts with VAT. Certified but not invoiced is the IPCs' net due, after retention and advance recovery. Counts follow your permissions.",
				[currency]
			),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { billing, retention, advance, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_owed(data, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Billed this month"),
				billing.restricted ? "—" : format_money(billing.month_amount, currency),
				note(
					billing.restricted
						? __("You do not have access to sales invoices")
						: __("{0} invoices in {1}, before VAT", [billing.month_count, billing.month_label])
				)
			),
			kpi(
				__("Retention held by clients"),
				retention.restricted ? "—" : format_money(retention.balance, currency),
				note(
					retention.restricted
						? __("You do not have access to certificates and invoices")
						: retention.due.length
						? __("{0} due for release now", [format_money(retention.due.reduce((s, d) => s + d.amount, 0), currency)])
						: __("{0} released so far", [format_money(retention.released, currency)])
				)
			),
			kpi(
				__("Advance still to recover"),
				advance.restricted ? "—" : format_money(advance.outstanding, currency),
				note(
					advance.restricted
						? __("You do not have access to certificates and invoices")
						: !advance.billed
						? __("No advance billed")
						: __("{0} of {1} recovered on certificates", [format_money(advance.recovered, currency), format_money(advance.billed, currency)])
				)
			),
			health_kpi(data.health)
		)
	);
}

// The clients owe us what is invoiced and unpaid, and what they have certified but we have not yet invoiced.
function render_owed(data, currency) {
	const { receivable, ipcs } = data;
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Certified but not invoiced, plus receivable") }));
	if (receivable.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to sales invoices.") }));
		return card;
	}
	const unbilled = ipcs.restricted ? 0 : ipcs.certified_unbilled;
	const total = receivable.total + unbilled;
	const share = total ? Math.round((receivable.total / total) * 1000) / 10 : 100;
	card.append(
		el("p", { class: "ov-hero-figure" }, el("span", { class: "ov-hero-value", text: format_money(total, currency) })),
		el(
			"div",
			{ class: "ov-stack-track", role: "img",
			  "aria-label": __("{0} receivable, {1} certified not invoiced", [format_money(receivable.total, currency), format_money(unbilled, currency)]) },
			el("span", { class: "ov-stack-receivable", style: `width: ${Math.min(share, 100)}%` }),
			unbilled ? el("span", { class: "ov-stack-unbilled", style: `width: ${Math.max(0, 100 - share)}%` }) : null
		),
		el("p", {
			class: "ov-hero-caption",
			text: ipcs.restricted
				? __("{0} owed on {1} open invoices, {2} of it overdue", [format_money(receivable.total, currency), receivable.count, format_money(receivable.overdue, currency)])
				: __("{0} owed on {1} open invoices ({2} overdue) + {3} certified on {4} IPCs not yet invoiced", [
						format_money(receivable.total, currency),
						receivable.count,
						format_money(receivable.overdue, currency),
						format_money(unbilled, currency),
						ipcs.certified_unbilled_count,
				  ]),
		}),
		report_link(
			"Accounts Receivable",
			{ company: frappe.defaults.get_user_default("Company") },
			[el("span", { text: __("Open accounts receivable") }), icon("chevron", "ov-chevron")],
			{ class: "ov-hero-link" }
		)
	);
	return card;
}

// ---------- Recent invoices ----------

function render_recent(recent, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (recent.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to sales invoices.") }));
		return card;
	}
	if (!recent.list.length) {
		card.append(el("p", { class: "ov-empty", text: __("No invoices yet.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			recent.list.map((row) =>
				el(
					"li",
					{},
					form_link(
						"Sales Invoice",
						row.name,
						[
							row_text(
								`${row.kind} · ${row.award_title || row.customer}`,
								[row.name, pretty_date(row.posting_date), row.outstanding > 0.005 ? __("{0} unpaid", [format_money(row.outstanding, currency)]) : __("Paid")].join(" · ")
							),
							el("span", { class: "ov-row-when", text: format_money(row.amount, currency) }),
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

function award_breakdown(billing, currency) {
	const rows = billing.restricted ? [] : billing.by_award;
	return {
		title: __("Billed by award, before VAT"),
		doctype: "Sales Invoice",
		field: "awarded_quotation",
		filters: billing.restricted ? {} : billing.filters,
		restricted: billing.restricted,
		measure: "amount",
		currency,
		rows,
		total: billing.restricted ? 0 : billing.total,
	};
}

function ageing_breakdown(receivable, currency) {
	const rows = receivable.restricted ? [] : receivable.ageing.filter((row) => row.count);
	return {
		title: __("Receivable by age"),
		doctype: "Sales Invoice",
		field: "due_date",
		filters: receivable.restricted ? {} : receivable.filters,
		restricted: receivable.restricted,
		measure: "amount",
		currency,
		rows,
		total: receivable.restricted ? 0 : receivable.total,
	};
}

function ipc_breakdown(ipcs) {
	const rows = ipcs.restricted ? [] : ipcs.by_status;
	return {
		title: __("IPCs by status"),
		doctype: "Client IPC",
		field: "status",
		filters: ipcs.restricted ? {} : ipcs.filters,
		restricted: ipcs.restricted,
		rows,
		total: rows.reduce((sum, row) => sum + row.count, 0),
	};
}

function retention_breakdown(retention, currency) {
	const rows = retention.restricted ? [] : retention.by_award;
	return {
		title: __("Retention held, by award"),
		doctype: "Client IPC",
		field: "awarded_quotation",
		filters: retention.restricted ? {} : retention.filters,
		restricted: retention.restricted,
		measure: "amount",
		currency,
		rows,
		total: retention.restricted ? 0 : retention.balance,
	};
}

// ---------- Billed and collected per month ----------

function render_trend_section(trend_part, currency) {
	const title = __("Billed and collected per month");
	if (trend_part.restricted) {
		return section({
			title,
			caption: __("Sales invoices and customer receipts"),
			body: el("div", { class: "ov-card ov-chart-card" }, el("p", { class: "ov-empty", text: __("You do not have access to sales invoices or payments.") })),
		});
	}
	const { trend } = trend_part;
	const billed = trend.reduce((sum, m) => sum + m.billed, 0);
	const collected = trend.reduce((sum, m) => sum + m.collected, 0);
	const chart = render_trend_chart(trend, currency);
	const table = render_table(
		[__("Month"), __("Billed (with VAT)"), __("Invoices"), __("Collected"), __("Receipts")],
		trend.map((m) => [m.label, format_money(m.billed, currency), format_count(m.billed_count), format_money(m.collected, currency), format_count(m.collected_count)])
	);
	table.classList.add("ov-trend-table");
	return section({
		title,
		caption: __("Last 12 months: {0} invoiced to clients, {1} received from them.", [format_money(billed, currency), format_money(collected, currency)]),
		body: el("div", { class: "ov-card ov-chart-card" }, chart, table),
		action: billed || collected ? chart_with_table(chart, table) : null,
	});
}

// Paired columns per month: invoiced (amber) beside received (green).
function render_trend_chart(trend, currency) {
	const max = Math.max(0, ...trend.flatMap((m) => [m.billed, m.collected]));
	if (!max) {
		return el("p", { class: "ov-empty", text: __("Nothing billed or collected in the last 12 months.") });
	}
	const { top, step } = nice_scale(max);
	const figure = el("figure", { class: "ov-chart", style: `--ov-count: ${trend.length}` });
	const legend = el(
		"div",
		{ class: "ov-legend ov-chart-legend" },
		el("span", {}, el("span", { class: "ov-swatch is-billed" }), el("span", { text: __("Billed") })),
		el("span", {}, el("span", { class: "ov-swatch is-collected" }), el("span", { text: __("Collected") }))
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
		const billed_bar = bar(m.billed, "billed");
		const collected_bar = bar(m.collected, "collected");
		const billed = format_money(m.billed, currency);
		const collected = format_money(m.collected, currency);
		const column = el(
			"div",
			{ class: "ov-col", tabindex: "0", role: "img", "aria-label": __("{0}: {1} billed, {2} collected", [m.label, billed, collected]) },
			el("div", { class: "ov-col-pair" }, billed_bar, collected_bar)
		);
		attach_tooltip(figure, column, m.billed >= m.collected ? billed_bar : collected_bar, __("{0} billed · {1} collected", [billed, collected]), m.label);
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
	api: "a3_constructa.api.sales_billing_overview.get_overview",
	storage_key: "a3_constructa.sales_billing.tab",
	labels: { overview: __("Sales & Billing Overview"), menu: __("Sales & Billing") },
	intro: __("What the clients owe us, what is certified and not yet invoiced, and the retention and advances still to settle."),
	render,
});
