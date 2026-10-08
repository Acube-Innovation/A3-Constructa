// Procurement Overview: tab 1 of the Procurement workspace.
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "Procurement Overview" Custom HTML Block on every `bench migrate`
// (a3_constructa/setup/custom_html_blocks.py). Edit them here, not in the desk.
//
// Tabs, loading, links and the common charts come from _shared/overview.js.

function render(data) {
	const { awards, currency } = data;
	return [
		render_summary(data),
		section({
			title: __("Procurement by award"),
			caption: __(
				"How much of each active award's approved BOQ has been requested, ordered and received, weighted by budget. Open one for its detail."
			),
			body: awards.restricted
				? restricted_card(__("Procurement by award needs read access to awards, BOQs and the buying documents."))
				: render_award_rows(awards.rows, currency, __("No active awards yet.")),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention"),
				caption: __("Orders running late and steps waiting on someone"),
				body: render_health(data.health),
			}),
			section({
				title: __("Recent purchase orders"),
				caption: __("The newest orders, drafts included"),
				body: render_recent_orders(data.orders, currency),
			})
		),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Waiting for approval"),
				caption: __("Requests and orders still to pass their approval levels, longest waiting first"),
				body: render_approvals(data.approvals, currency),
			}),
			section({
				title: __("Subcontract accounts"),
				caption: __("What the work certificates have certified, what was held back, and what is still to pay"),
				body: render_subcontracts(data.subcontracts, currency),
			})
		),
		section({
			title: __("Pipeline"),
			caption: __("Where every buying document stands. Open a row to see those documents."),
			body: el("div", { class: "ov-breakdowns" }, pipeline(data).map(render_breakdown)),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Top suppliers"),
				caption: __("Submitted purchase orders over the last 12 months"),
				body: render_breakdown(suppliers(data.orders, currency)),
			}),
			section({
				title: __("Shipments on the way"),
				caption: __("Tracked shipments not yet received"),
				body: render_breakdown(shipments(data.shipments)),
			})
		),
		el("p", {
			class: "ov-footnote",
			text: __("Money is shown in {0}, the company's default currency. Counts follow your permissions.", [
				currency,
			]),
		}),
	];
}

// ---------- Summary ----------

function render_summary(data) {
	const { orders, requests, awards, approvals, currency } = data;
	return el(
		"div",
		{ class: "ov-summary" },
		render_open_orders(orders, awards, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Requests waiting for an order"),
				requests.restricted ? "—" : format_count(requests.waiting_count),
				note(
					requests.restricted
						? __("You do not have access to material requests")
						: requests.waiting_count
						? __("The oldest has waited {0} days", [requests.oldest_days])
						: __("None waiting")
				)
			),
			kpi(
				__("Awaiting approval"),
				approvals.restricted ? "—" : format_count(approvals.count),
				note(
					approvals.restricted
						? __("You do not have access to requests or orders")
						: approvals.count
						? __("Worth {0} · {1} waiting on you", [format_money(approvals.value, currency), approvals.mine])
						: __("Nothing waiting")
				)
			),
			kpi(
				__("Awarded BOQs on order"),
				awards.restricted ? "—" : `${Math.round(awards.ordered)}%`,
				note(
					awards.restricted
						? __("You do not have access to awards")
						: __("{0} committed against {1} budget", [
								format_money(awards.committed, currency),
								format_money(awards.budget, currency),
						  ])
				)
			),
			health_kpi(data.health)
		)
	);
}

function render_open_orders(orders, awards, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Still to arrive") }));
	if (orders.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to purchase orders.") }));
		return card;
	}
	card.append(
		el(
			"p",
			{ class: "ov-hero-figure" },
			el("span", { class: "ov-hero-value ov-hero-money", text: format_money(orders.open_value, currency) })
		),
		el("p", {
			class: "ov-hero-caption",
			text:
				orders.open_count === 1
					? __("Goods and services not yet received on 1 open purchase order")
					: __("Goods and services not yet received on {0} open purchase orders", [orders.open_count]),
		})
	);
	if (orders.late_count) {
		card.append(
			el(
				"p",
				{ class: "ov-hero-issue" },
				icon("critical", "is-critical"),
				el("span", {
					text:
						orders.late_count === 1
							? __("1 is past its delivery date")
							: __("{0} are past their delivery date", [orders.late_count]),
				})
			)
		);
	}
	if (!awards.restricted && awards.rows.length) {
		card.append(
			el(
				"div",
				{ class: "ov-hero-stages" },
				el("p", { class: "ov-label", text: __("Active awards, all approved BOQs") }),
				render_stages(awards_total(awards), __("Active awards")),
				stage_figures(awards_total(awards), { labelled: true })
			)
		);
	}
	return card;
}

// Budget-weighted stages across every active award.
function awards_total(awards) {
	const budget = awards.rows.reduce((sum, row) => sum + row.budget, 0);
	const weigh = (key) =>
		budget ? awards.rows.reduce((sum, row) => sum + row.budget * row[key], 0) / budget : 0;
	return { requested: weigh("requested"), ordered: weigh("ordered"), received: weigh("received") };
}

// ---------- Lists ----------

function render_recent_orders(orders, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (orders.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to purchase orders.") }));
		return card;
	}
	if (!orders.recent.length) {
		card.append(el("p", { class: "ov-empty", text: __("No purchase orders yet.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			orders.recent.map((order) =>
				el(
					"li",
					{},
					form_link(
						"Purchase Order",
						order.name,
						[
							row_text(
								order.supplier,
								`${order.name} · ${__(order.status)} · ${__("due {0}", [format_date(order.schedule_date)])}`
							),
							el("span", { class: "ov-row-when", text: format_money(order.base_net_total, currency) }),
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

function render_approvals(approvals, currency) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (approvals.restricted) {
		card.append(el("p", { class: "ov-empty", text: __("You do not have access to requests or orders.") }));
		return card;
	}
	if (!approvals.list.length) {
		card.append(el("p", { class: "ov-empty", text: __("Nothing is waiting for approval.") }));
		return card;
	}
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			approvals.list.map((row) =>
				el(
					"li",
					{},
					form_link(
						row.document_type,
						row.document,
						[
							row.is_rejected
								? icon("critical", "is-critical")
								: row.age_days > approvals.wait_days
								? icon("warning", "is-warning")
								: icon("empty", "is-muted"),
							row_text(
								`${row.document} · ${format_money(row.value, currency)}`,
								`${row.status} · ${row.is_mine ? __("you") : row.approver}`
							),
							el("span", {
								class: row.age_days > approvals.wait_days ? "ov-row-when is-late" : "ov-row-when",
								text: row.age_days === 1 ? __("1 day") : __("{0} days", [row.age_days]),
							}),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row" }
					)
				)
			)
		),
		el(
			"p",
			{ class: "ov-list-foot" },
			report_link(
				"Approvals Pending",
				{},
				approvals.rejected
					? __("All {0} in Approvals Pending, {1} rejected and back with the requester", [
							approvals.count + approvals.rejected,
							approvals.rejected,
					  ])
					: __("All {0} in Approvals Pending", [approvals.count]),
				{ class: "ov-text-link" }
			)
		)
	);
	return card;
}

function render_subcontracts(part, currency) {
	if (part.restricted) {
		return restricted_card(__("Subcontract accounts need read access to work certificates and purchase orders."));
	}
	const card = el("div", { class: "ov-card ov-list-card" });
	if (!part.count) {
		card.append(el("p", { class: "ov-empty", text: __("No subcontract certified yet.") }));
		return card;
	}
	card.append(
		el(
			"dl",
			{ class: "ov-totals" },
			el("dt", { text: __("Certified") }),
			el("dd", { text: format_money(part.certified, currency) }),
			el("dt", { text: __("Retention held") }),
			el("dd", { text: format_money(part.retention, currency) }),
			el("dt", { text: __("Back-charges and deductions") }),
			el("dd", { text: format_money(part.deductions, currency) }),
			el("dt", { text: __("Balance to pay") }),
			el("dd", { text: format_money(part.balance, currency) })
		),
		el(
			"ul",
			{ class: "ov-rows" },
			part.rows.map((row) =>
				el(
					"li",
					{},
					form_link(
						"Purchase Order",
						row.subcontract_po,
						[
							row.note ? icon("warning", "is-warning") : icon("empty", "is-muted"),
							row_text(
								row.supplier,
								[
									row.subcontract_po,
									row.certified_percent === null
										? null
										: __("{0}% certified", [Math.round(row.certified_percent)]),
									row.note || null,
								]
									.filter(Boolean)
									.join(" · ")
							),
							el("span", { class: "ov-row-when", text: format_money(row.balance, currency) }),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row" }
					)
				)
			)
		)
	);
	const wrap = el("div", { class: "ov-stack" }, card);
	if (part.by_deduction.length) {
		wrap.append(
			render_breakdown({
				title: __("Held back by type"),
				doctype: "Work Certificate",
				field: "name",
				filters: {},
				measure: "amount",
				currency,
				rows: part.by_deduction,
				total: part.deductions,
			})
		);
	}
	return wrap;
}

function restricted_card(text) {
	return el("div", { class: "ov-card" }, el("p", { class: "ov-empty", text }));
}

// ---------- Breakdowns ----------

function pipeline(data) {
	const { requests, quotes, orders } = data;
	const by_status = (title, doctype, rows, restricted, filters = {}) => ({
		title,
		doctype,
		field: "status",
		filters,
		restricted,
		rows: restricted ? [] : rows,
		total: restricted ? 0 : rows.reduce((sum, row) => sum + row.count, 0),
	});
	return [
		by_status(__("Material requests"), "Material Request", requests.by_status || [], requests.restricted, {
			material_request_type: "Purchase",
		}),
		by_status(__("Requests for quotation"), "Request for Quotation", quotes.rfq_by_status || [], quotes.rfq_restricted),
		by_status(__("Supplier quotations"), "Supplier Quotation", quotes.sq_by_status || [], quotes.sq_restricted),
		by_status(__("Purchase orders"), "Purchase Order", orders.by_status || [], orders.restricted),
	];
}

function suppliers(orders, currency) {
	return {
		title: __("By order value"),
		doctype: "Purchase Order",
		field: "supplier",
		filters: { docstatus: 1 },
		restricted: orders.restricted,
		measure: "amount",
		currency,
		rows: orders.restricted ? [] : orders.suppliers,
		total: orders.restricted ? 0 : orders.suppliers_total,
	};
}

function shipments(part) {
	return {
		title: __("By status"),
		doctype: "Shipment Tracking",
		field: "status",
		filters: { docstatus: ["<", 2] },
		restricted: part.restricted,
		rows: part.restricted ? [] : part.by_status,
		total: part.restricted ? 0 : part.active,
	};
}

mount_overview({
	api: "a3_constructa.api.procurement_overview.get_overview",
	storage_key: "a3_constructa.procurement.tab",
	labels: { overview: __("Procurement Overview"), menu: __("Procurement") },
	intro: __("Requests, approvals, quotations, orders, subcontracts and deliveries across A3 Constructa."),
	render,
});
