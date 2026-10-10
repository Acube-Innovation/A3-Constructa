// A3 Constructa Overview: tab 1 of the A3 Constructa home (D-15).
//
// The files in this folder, behind the shared ones in ../_shared/, are written
// into the "A3 Constructa Overview" Custom HTML Block on every `bench migrate`
// (a3_constructa/setup/custom_html_blocks.py). Edit them here, not in the desk.
//
// Every figure comes from the module overviews (api/home_overview.py): each card
// shows the figure its own tab leads with and opens that workspace.

function render(data) {
	const critical = data.health.filter((c) => c.severity === "critical");
	const warnings = data.health.filter((c) => c.severity !== "critical");
	return [
		render_summary(data, critical),
		section({
			title: __("Modules"),
			caption: __("Each card is a module's own headline, and how many of its checks need attention. Open one to go to its workspace."),
			body: render_modules(data.modules, data.currency),
		}),
		el(
			"div",
			{ class: "ov-split" },
			section({
				title: __("Needs attention: critical"),
				caption: __("From every module, the largest first"),
				body: critical.length ? render_health(critical) : all_clear(__("No critical checks in any module.")),
			}),
			section({
				title: __("Needs attention: warnings"),
				caption: __("Each names its module"),
				body: warnings.length ? render_health(warnings) : all_clear(__("No warnings in any module.")),
			})
		),
		el("p", {
			class: "ov-footnote",
			text: __(
				"Read from each module's overview for {0}. Money is in {1}, the company's default currency. A module you cannot open shows as such; counts follow your permissions.",
				[data.company, data.currency]
			),
		}),
	];
}

function all_clear(text) {
	return el("div", { class: "ov-card ov-list-card" }, el("p", { class: "ov-empty", text }));
}

// ---------- Summary ----------

function render_summary(data, critical) {
	const { book, projects, alerts, currency } = data;
	const failing = data.health.length;
	const worst = critical.length ? "critical" : failing ? "warning" : "good";
	return el(
		"div",
		{ class: "ov-summary" },
		render_book(book, currency),
		el(
			"div",
			{ class: "ov-kpis" },
			kpi(
				__("Active projects"),
				projects.restricted ? "—" : format_count(projects.count),
				note(projects.restricted ? __("You do not have access to the programme") : __("{0}% complete against {1}% planned", [projects.percent, projects.planned]))
			),
			kpi(__("Critical checks"), format_count(critical.length), note(__("across {0} modules", [new Set(critical.map((c) => c.module)).size])), critical.length ? icon("critical", "is-critical") : icon("good", "is-good")),
			kpi(__("Alerts sent, 7 days"), alerts.restricted ? "—" : format_count(alerts.count), note(alerts.restricted ? __("You do not have access to alert rules") : __("by the alert rules"))),
			kpi(__("Checks needing attention"), format_count(failing), note(__("{0} of {1} checks found gaps", [failing, data.measured])), icon(worst, `is-${worst}`))
		)
	);
}

function render_book(book, currency) {
	const card = el("div", { class: "ov-card ov-hero" }, el("p", { class: "ov-label", text: __("Order book") }));
	if (book.restricted) {
		card.append(el("p", { class: "ov-hero-caption", text: __("You do not have access to the awards.") }));
		return card;
	}
	card.append(
		el("p", { class: "ov-hero-figure" }, el("span", { class: "ov-hero-value", text: format_money(book.value, currency) })),
		el("p", { class: "ov-hero-caption", text: __("Revised contract value of {0} active awards", [book.active]) })
	);
	if (book.earned !== null && book.earned !== undefined) {
		card.append(
			el(
				"ul",
				{ class: "ov-home-facts" },
				el("li", {}, el("span", { text: __("Earned by the work done") }), el("b", { text: format_money(book.earned, currency) })),
				el("li", {}, el("span", { text: __("Billed to date") }), el("b", { text: format_money(book.billed, currency) }))
			)
		);
	}
	card.append(workspace_link("/app/contracts-%26-awards", [el("span", { text: __("Open Contracts & Awards") }), icon("chevron", "ov-chevron")], { class: "ov-hero-link" }));
	return card;
}

// ---------- Module cards ----------

function render_modules(modules, currency) {
	return el(
		"ul",
		{ class: "ov-modules" },
		modules.map((m) => el("li", {}, workspace_link(m.route, module_card(m, currency), { class: "ov-module", "aria-label": m.label })))
	);
}

function module_card(m, currency) {
	const head = el("div", { class: "ov-module-head" }, el("span", { class: "ov-module-division", text: m.division }), el("span", { class: "ov-module-name", text: m.label }), icon("chevron", "ov-chevron"));
	if (m.restricted || m.failed) {
		return [head, el("p", { class: "ov-module-note", text: m.failed ? __("Could not load just now") : __("You do not have access to this module") })];
	}
	const h = m.headline;
	const value = h.restricted ? "—" : h.kind === "money" ? format_money(h.value, currency) : h.kind === "percent" ? `${Math.round(h.value * 10) / 10}%` : format_count(h.value);
	const status = m.critical
		? el("span", { class: "ov-chip is-critical", text: __("{0} critical", [m.critical]) })
		: null;
	const warn = m.warning ? el("span", { class: "ov-chip is-warning", text: m.warning === 1 ? __("1 warning") : __("{0} warnings", [m.warning]) }) : null;
	const ok = !m.critical && !m.warning ? el("span", { class: "ov-chip is-good", text: m.checks ? __("All clear") : __("No checks open to you") }) : null;
	return [
		head,
		el("p", { class: "ov-module-label", text: h.label }),
		el("p", { class: "ov-module-value", text: value }),
		el("p", { class: "ov-module-note", text: h.restricted ? __("You do not have access to this figure") : h.note || "" }),
		el("div", { class: "ov-module-chips" }, status, warn, ok),
	];
}

// A workspace is a page of its own: a plain click routes inside the desk.
function workspace_link(href, content, attrs = {}) {
	const link = el("a", { ...attrs, href }, content);
	link.addEventListener("click", (event) => {
		if (!is_plain_click(event)) return;
		event.preventDefault();
		frappe.router.push_state(href);
	});
	return link;
}

mount_overview({
	api: "a3_constructa.api.home_overview.get_overview",
	storage_key: "a3_constructa.home.tab",
	labels: { overview: __("A3 Constructa Overview"), menu: __("A3 Constructa") },
	intro: __("The whole company at a glance: the order book, each module's headline, and everything that needs attention."),
	render,
});
