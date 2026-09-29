// Shared by every overview block.
//
// custom_html_blocks.py puts this file in front of each block's own script, so
// everything here is a plain function in the same scope as the block's code.
// A workspace block ends by calling mount_overview() with its API method, tab
// labels and a render function; a block shown on its own page (no tabs) calls
// mount_view() instead. This file does the rest.
//
// Frappe runs the combined script with `root_element` bound to the block's
// shadow root.
//
// Tab 1 is drawn inside the block. Tab 2 is the workspace itself: the blocks
// after this one are ordinary workspace blocks, edited the normal way. While
// tab 1 shows, a page-level rule (PAGE_CSS) hides those sibling blocks;
// choosing tab 2 lifts it.

const PAGE_STYLE_ID = "a3-overview-tabs";
const PAGE_CSS = `
/* a3_constructa, workspace overview tabs. While an Overview tab is selected,
   hide the other blocks of the workspace that holds it. :has() pins the rule to
   that one editor, and :not(.edit-mode) keeps every card visible while the
   workspace is being edited. */
.layout-main-section:not(.edit-mode) .codex-editor__redactor:has(> .ce-block[data-a3-tab="overview"]) > .ce-block:not([data-a3-tab]) {
	display: none;
}
.ce-block[data-a3-tab] .custom-block-widget-box {
	padding: 0;
}
`;

// The MASECO faces. A font declared inside a shadow root is never loaded, so
// the stylesheet goes in the page's own <head>, once, and the block uses it.
const FONTS_ID = "a3-maseco-fonts";
const FONTS_URL =
	"https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,300;6..72,400;6..72,500&family=Public+Sans:wght@400;500;600;700&display=swap";

// 16px stroke icons. Status glyphs are filled so the colour reads at this size;
// each one always sits next to a text label.
const ICONS = {
	good: '<circle cx="8" cy="8" r="7" fill="currentColor" stroke="none"/><path class="mark" d="M5 8.2l2 2 4-4.4"/>',
	warning: '<path d="M8 1.5 15.2 14H.8z" fill="currentColor" stroke="none"/><path class="mark" d="M8 6v3.5M8 11.6v.01"/>',
	critical: '<circle cx="8" cy="8" r="7" fill="currentColor" stroke="none"/><path class="mark" d="M8 4.6v4M8 11.2v.01"/>',
	empty: '<circle cx="8" cy="8" r="5.75"/>',
	lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>',
	refresh: '<path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/><path d="M13.5 2.5v3h-3"/>',
	chevron: '<path d="M6 3.5 10.5 8 6 12.5"/>',
	up: '<path d="M8 13V3.5"/><path d="M4 7.5 8 3.5l4 4"/>',
	down: '<path d="M8 3v9.5"/><path d="M4 8.5l4 4 4-4"/>',
};

const host = root_element.host;
const block = host.closest(".ce-block");
const workspace_body = host.closest(".layout-main-section");
const app = root_element.querySelector(".ov");
const panel = root_element.querySelector(".ov-panel");
const editing_note = root_element.querySelector(".ov-editing-note");
const tab_buttons = [...root_element.querySelectorAll(".ov-tab")];

let overview_config = null;
let overview_data = null;
let overview_loading = false;

// config: { api, args?, storage_key, labels: { overview, menu }, intro, render(data) -> nodes }
function mount_overview(config) {
	overview_config = config;
	install_fonts();
	install_page_style();
	set_static_text();
	sync_theme();
	sync_edit_mode();
	watch(document.documentElement, ["data-theme"], sync_theme);
	watch(workspace_body, ["class"], sync_edit_mode);
	bind_tabs();
	select_tab(remembered_tab());
}

// A block on a page of its own: no tabs, just the panel.
// config: { api, args?, intro, render(data) -> nodes }
function mount_view(config) {
	overview_config = config;
	install_fonts();
	sync_theme();
	watch(document.documentElement, ["data-theme"], sync_theme);
	load_overview();
}

// ---------- Tabs and page wiring ----------

function install_fonts() {
	if (document.getElementById(FONTS_ID)) return;
	document.head.append(el("link", { id: FONTS_ID, rel: "stylesheet", href: FONTS_URL }));
}

function install_page_style() {
	let style = document.getElementById(PAGE_STYLE_ID);
	if (!style) {
		style = document.createElement("style");
		style.id = PAGE_STYLE_ID;
		document.head.append(style);
	}
	style.textContent = PAGE_CSS;
}

function set_static_text() {
	const { labels } = overview_config;
	tab_buttons[0].textContent = labels.overview;
	tab_buttons[1].textContent = labels.menu;
	root_element.querySelector(".ov-tabs").setAttribute("aria-label", labels.menu);
	editing_note.textContent = __(
		"The overview is hidden while you edit. Everything below this block is the {0} tab.",
		[labels.menu]
	);
}

function bind_tabs() {
	for (const button of tab_buttons) {
		button.addEventListener("click", () => select_tab(button.dataset.tab));
		button.addEventListener("keydown", (event) => {
			const index = tab_buttons.indexOf(button);
			const last = tab_buttons.length - 1;
			const target = {
				ArrowRight: index === last ? 0 : index + 1,
				ArrowLeft: index === 0 ? last : index - 1,
				Home: 0,
				End: last,
			}[event.key];
			if (target === undefined) return;
			event.preventDefault();
			select_tab(tab_buttons[target].dataset.tab, { focus: true });
		});
	}
}

function select_tab(tab, { focus = false } = {}) {
	app.dataset.tab = tab;
	// Read by PAGE_CSS to show or hide the workspace's own blocks.
	if (block) block.dataset.a3Tab = tab;

	for (const button of tab_buttons) {
		const selected = button.dataset.tab === tab;
		button.setAttribute("aria-selected", String(selected));
		button.tabIndex = selected ? 0 : -1;
		if (selected && focus) button.focus();
	}
	panel.hidden = tab !== "overview";

	try {
		sessionStorage.setItem(overview_config.storage_key, tab);
	} catch (e) {
		// Storage blocked: the tab is simply not remembered.
	}
	if (tab === "overview" && !overview_data && !overview_loading) load_overview();
}

// Remembered for the browser session only, so every new session opens on the overview.
function remembered_tab() {
	try {
		return sessionStorage.getItem(overview_config.storage_key) === "menu" ? "menu" : "overview";
	} catch (e) {
		return "overview";
	}
}

function watch(target, attributes, callback) {
	if (!target) return;
	const observer = new MutationObserver(() => {
		// Frappe rebuilds the editor when you leave the workspace; stop with it.
		if (!host.isConnected) return observer.disconnect();
		callback();
	});
	observer.observe(target, { attributes: true, attributeFilter: attributes });
}

function sync_theme() {
	app.dataset.theme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function sync_edit_mode() {
	const editing = Boolean(workspace_body && workspace_body.classList.contains("edit-mode"));
	app.classList.toggle("is-editing", editing);
	editing_note.hidden = !editing;
}

// ---------- Data ----------

async function load_overview() {
	overview_loading = true;
	app.classList.toggle("is-refreshing", Boolean(overview_data));
	panel.setAttribute("aria-busy", "true");
	for (const button of root_element.querySelectorAll(".ov-refresh")) button.disabled = true;
	if (!overview_data) panel.replaceChildren(render_skeleton());

	try {
		const data = await frappe.xcall(overview_config.api, overview_config.args || {});
		panel.replaceChildren(render_toolbar(data), ...overview_config.render(data));
		overview_data = data;
	} catch (error) {
		// A server error has already been shown by frappe.xcall; a drawing error
		// has not, so log it. Keep the last good render if this was a refresh.
		console.error(error);
		if (!overview_data) panel.replaceChildren(render_error());
		for (const button of root_element.querySelectorAll(".ov-refresh")) button.disabled = false;
	} finally {
		overview_loading = false;
		app.classList.remove("is-refreshing");
		panel.removeAttribute("aria-busy");
	}
}

function render_toolbar(data) {
	return el(
		"div",
		{ class: "ov-toolbar" },
		el("p", { class: "ov-intro", text: overview_config.intro }),
		el(
			"div",
			{ class: "ov-stamp" },
			el("span", { text: __("As of {0}", [format_time(data.generated_at)]) }),
			el(
				"button",
				{ type: "button", class: "ov-button ov-refresh", onclick: () => load_overview() },
				icon("refresh"),
				__("Refresh")
			)
		)
	);
}

function render_skeleton() {
	return el(
		"div",
		{ class: "ov-skeleton", role: "status", "aria-label": __("Loading the overview") },
		el("span"),
		el("span"),
		el("span")
	);
}

function render_error() {
	return el(
		"div",
		{ class: "ov-error" },
		el("p", { text: __("The overview could not be loaded.") }),
		el(
			"button",
			{ type: "button", class: "ov-button", onclick: () => load_overview() },
			icon("refresh"),
			__("Try again")
		)
	);
}

// ---------- Building blocks ----------

function section({ title, caption, body, action = null }) {
	return el(
		"section",
		{ class: "ov-section" },
		el(
			"div",
			{ class: "ov-section-head" },
			el(
				"div",
				{},
				el("h3", { class: "ov-section-title", text: title }),
				caption ? el("p", { class: "ov-section-caption", text: caption }) : null
			),
			action
		),
		body
	);
}

// The figure is coloured by state: attention when a warning or critical icon
// leads it, quiet when there is nothing to count ("0", "—", "₹ 0").
function kpi(label, value, note_element, value_icon = null) {
	const attention = value_icon && /\bis-(warning|critical)\b/.test(value_icon.className);
	const state = attention ? "is-attention" : /[1-9]/.test(value) ? "" : "is-zero";
	return el(
		"div",
		{ class: `ov-card ov-kpi ${state}`.trim() },
		el("p", { class: "ov-label", text: label }),
		el("p", { class: "ov-kpi-value" }, value_icon, el("span", { text: value })),
		note_element
	);
}

function note(text, note_icon = null) {
	return el("p", { class: "ov-kpi-note" }, note_icon, el("span", { text }));
}

// The count of failing checks, with the worst severity as its icon.
function health_kpi(checks) {
	const measured = checks.filter((check) => check.count !== null);
	const failing = measured.filter((check) => check.count > 0);
	const worst = failing.some((check) => check.severity === "critical")
		? "critical"
		: failing.length
		? "warning"
		: "good";
	return kpi(
		__("Checks needing attention"),
		format_count(failing.length),
		note(
			failing.length
				? __("{0} of {1} checks found gaps", [failing.length, measured.length])
				: __("All {0} checks pass", [measured.length])
		),
		icon(worst, `is-${worst}`)
	);
}

// checks: [{ label, severity, doctype, count (null = no access), filters, meta }]
function render_health(checks) {
	return el(
		"div",
		{ class: "ov-card ov-list-card" },
		el(
			"ul",
			{ class: "ov-rows" },
			checks.map((check) => el("li", {}, render_check(check)))
		)
	);
}

function render_check(check) {
	if (check.count === null) {
		return el(
			"div",
			{ class: "ov-row is-ok" },
			icon("lock", "is-muted"),
			row_text(check.label, __("You do not have access to {0}", [__(check.doctype)])),
			el("span", { class: "ov-row-count", text: "—" })
		);
	}
	if (!check.count) {
		return el(
			"div",
			{ class: "ov-row is-ok" },
			icon("good", "is-good"),
			row_text(check.label, __("All clear")),
			el("span", { class: "ov-row-count", text: "0" })
		);
	}
	const severity = check.severity === "critical" ? __("Critical") : __("Warning");
	const open = check.report
		? (content, attrs) => report_link(check.report, check.filters, content, attrs)
		: (content, attrs) => list_link(check.doctype, check.filters, content, attrs);
	return open(
		[
			icon(check.severity, `is-${check.severity}`),
			row_text(check.label, [severity, check.meta || __(check.doctype)].join(" · ")),
			el("span", { class: "ov-row-count", text: format_count(check.count) }),
			icon("chevron", "ov-chevron"),
		],
		{ class: "ov-row" }
	);
}

function row_text(title, meta) {
	return el(
		"span",
		{ class: "ov-row-main" },
		el("span", { class: "ov-row-title", text: title, title }),
		el("span", { class: "ov-row-meta", text: meta })
	);
}

// A ranked bar list; each row opens the list filtered to it.
// breakdown: { title, doctype, field, filters, restricted, total, currency?,
//              measure?: "count" | "amount", rows: [{ label, value, count, amount?, other? }] }
// With measure "amount" the bars, labels and total are money in `currency`.
function render_breakdown(breakdown) {
	const card = el(
		"div",
		{ class: "ov-card ov-breakdown" },
		el(
			"div",
			{ class: "ov-breakdown-head" },
			el("h4", { class: "ov-breakdown-title", text: breakdown.title }),
			breakdown.restricted
				? null
				: el("span", {
						class: "ov-breakdown-total",
						text: __("{0} in total", [measure_text(breakdown, breakdown.total)]),
				  })
		)
	);

	if (breakdown.restricted) {
		card.append(
			el("p", { class: "ov-empty", text: __("You do not have access to {0}", [__(breakdown.doctype)]) })
		);
		return card;
	}
	if (!breakdown.rows.length) {
		card.append(el("p", { class: "ov-empty", text: __("No records yet.") }));
		return card;
	}

	const size = (row) => (breakdown.measure === "amount" ? row.amount : row.count);
	const max = Math.max(...breakdown.rows.map(size));
	const list = el("ul", { class: "ov-bars" });

	for (const row of breakdown.rows) {
		const share = breakdown.total ? Math.round((size(row) / breakdown.total) * 100) : 0;
		const filters = { ...(breakdown.filters || {}) };
		if (!row.other) filters[breakdown.field] = row.value === null ? ["is", "not set"] : row.value;

		// Leave room at the end of the track for the value label.
		const bar = el("span", {
			class: row.other ? "ov-bar is-other" : "ov-bar",
			style: `width: calc((100% - var(--ov-bar-label-room, 48px)) * ${max ? size(row) / max : 0})`,
		});
		const link = list_link(
			breakdown.doctype,
			filters,
			[
				el("span", { class: "ov-bar-label", text: row.label, title: row.label }),
				el(
					"span",
					{ class: "ov-bar-track" },
					bar,
					el("span", { class: "ov-bar-value", text: measure_text(breakdown, size(row)) })
				),
			],
			{
				class: "ov-bar-row",
				"aria-label": __("{0}: {1}, {2}% of {3}", [
					row.label,
					measure_text(breakdown, size(row)),
					share,
					measure_text(breakdown, breakdown.total),
				]),
			}
		);
		const detail = [
			__("{0} of {1}", [measure_text(breakdown, size(row)), measure_text(breakdown, breakdown.total)]),
		];
		if (breakdown.measure !== "amount" && row.amount !== undefined && breakdown.currency) {
			detail.push(format_money(row.amount, breakdown.currency));
		}
		attach_tooltip(card, link, bar, `${share}%`, detail.join(" · "));
		list.append(el("li", {}, link));
	}

	card.append(list);
	if (breakdown.measure === "amount") card.style.setProperty("--ov-bar-label-room", "110px");
	return card;
}

function measure_text(breakdown, value) {
	return breakdown.measure === "amount" ? format_money(value, breakdown.currency) : format_count(value);
}

// ---------- Procurement stages ----------

// One track, three layered fills: requested, ordered, received, each a share of
// the approved BOQ. Each stage normally follows the one before, so they are
// drawn in that order and the later, darker stage sits on top.
// stages: { requested, ordered, received } as percentages.
function render_stages(stages, label) {
	const layer = (key) =>
		el("span", { class: `ov-stage ov-stage-${key}`, style: `width: ${Math.min(100, Math.max(0, stages[key]))}%` });
	return el(
		"span",
		{
			class: "ov-stages",
			role: "img",
			"aria-label": __("{0}: requested {1}%, ordered {2}%, received {3}%", [
				label,
				Math.round(stages.requested),
				Math.round(stages.ordered),
				Math.round(stages.received),
			]),
		},
		layer("requested"),
		layer("ordered"),
		layer("received")
	);
}

// The three percentages beside their swatches. `labelled` names each stage,
// for places with no legend nearby.
function stage_figures(stages, { labelled = false } = {}) {
	const names = { requested: __("Requested"), ordered: __("Ordered"), received: __("Received") };
	return el(
		"span",
		{ class: "ov-stage-figures" },
		["requested", "ordered", "received"].map((key) =>
			el(
				"span",
				{},
				el("span", { class: `ov-swatch ov-stage-${key}` }),
				el("span", { text: labelled ? `${names[key]} ${Math.round(stages[key])}%` : `${Math.round(stages[key])}%` })
			)
		)
	);
}

function stage_legend() {
	return el(
		"div",
		{ class: "ov-legend" },
		[
			["requested", __("Requested")],
			["ordered", __("Ordered")],
			["received", __("Received")],
		].map(([key, text]) => el("span", {}, el("span", { class: `ov-swatch ov-stage-${key}` }), el("span", { text })))
	);
}

// Awards with how much of their approved BOQ has been bought, each opening its
// Award Procurement page. Budget and committed are in the company currency.
function render_award_rows(rows, currency, empty_text) {
	const card = el("div", { class: "ov-card ov-list-card" });
	if (!rows.length) {
		card.append(el("p", { class: "ov-empty", text: empty_text }));
		return card;
	}
	card.append(el("div", { class: "ov-list-legend" }, stage_legend()));
	card.append(
		el(
			"ul",
			{ class: "ov-rows" },
			rows.map((row) =>
				el(
					"li",
					{},
					page_link(
						"award-procurement",
						row.name,
						[
							el(
								"span",
								{ class: "ov-row-main" },
								el("span", { class: "ov-row-title", text: row.title, title: row.title }),
								el("span", { class: "ov-row-meta", text: `${row.customer} · ${__(row.status)}` })
							),
							row.lines
								? el("span", { class: "ov-progress-cell" }, render_stages(row, row.title), stage_figures(row))
								: el("span", {
										class: "ov-progress-cell ov-row-meta",
										text: __("Nothing to track until a BOQ is approved"),
								  }),
							row.lines
								? el(
										"span",
										{ class: "ov-money-cell" },
										el("strong", { text: format_money(row.committed, currency) }),
										el("span", { text: __("of {0} budget", [format_money(row.budget, currency)]) })
								  )
								: el("span", { class: "ov-money-cell" }, el("span", { text: __("No approved BOQ") })),
							icon("chevron", "ov-chevron"),
						],
						{ class: "ov-row ov-progress-row" }
					)
				)
			)
		)
	);
	return card;
}

// One tooltip per chart. The value leads; the label follows.
function attach_tooltip(container, target, anchor, value, label) {
	const show = () => {
		let tip = container.querySelector(":scope > .ov-tooltip");
		if (!tip) {
			tip = el("div", { class: "ov-tooltip", role: "tooltip" });
			container.append(tip);
		}
		tip.replaceChildren(el("strong", { text: value }), el("span", { text: label }));
		tip.hidden = false;
		const box = container.getBoundingClientRect();
		const mark = anchor.getBoundingClientRect();
		// Centre over the mark, but keep the whole tooltip inside the chart.
		const half = tip.offsetWidth / 2 + 4;
		const centre = mark.left - box.left + mark.width / 2;
		tip.style.left = `${Math.min(Math.max(centre, half), box.width - half)}px`;
		tip.style.top = `${mark.top - box.top}px`;
	};
	const hide = () => {
		const tip = container.querySelector(":scope > .ov-tooltip");
		if (tip) tip.hidden = true;
	};
	target.addEventListener("pointerenter", show);
	target.addEventListener("focus", show);
	target.addEventListener("pointerleave", hide);
	target.addEventListener("blur", hide);
}

// A chart and its table, with a button in the section header to swap them.
function chart_with_table(chart, table) {
	table.hidden = true;
	const toggle = el("button", { type: "button", class: "ov-button", "aria-pressed": "false" }, __("Show table"));
	toggle.addEventListener("click", () => {
		const show_table = table.hidden;
		table.hidden = !show_table;
		chart.hidden = show_table;
		toggle.textContent = show_table ? __("Show chart") : __("Show table");
		toggle.setAttribute("aria-pressed", String(show_table));
	});
	return toggle;
}

function render_table(headers, rows) {
	return el(
		"div",
		{ class: "ov-table-wrap" },
		el(
			"table",
			{ class: "ov-table" },
			el("thead", {}, el("tr", {}, headers.map((text) => el("th", { scope: "col", text })))),
			el("tbody", {}, rows.map((cells) => el("tr", {}, cells.map((text) => el("td", { text })))))
		)
	);
}

// Round the axis up to 1, 2 or 5 x 10^n, aiming for about four gridlines.
function nice_scale(max) {
	const raw = Math.max(1, max / 4);
	const magnitude = 10 ** Math.floor(Math.log10(raw));
	const step = [1, 2, 5, 10].map((m) => m * magnitude).find((candidate) => candidate >= raw);
	return { step, top: Math.ceil(max / step) * step };
}

// ---------- Links, DOM and formatting ----------

// Links keep a real href so ctrl/cmd-click opens a new tab; a plain click
// routes inside the desk with the filters applied.
function list_link(doctype, filters, content, attrs = {}) {
	const link = el("a", { ...attrs, href: `/app/${frappe.router.slug(doctype)}` }, content);
	link.addEventListener("click", (event) => {
		if (!is_plain_click(event)) return;
		event.preventDefault();
		frappe.route_options = { ...filters };
		frappe.set_route("List", doctype);
	});
	return link;
}

function report_link(report, filters, content, attrs = {}) {
	const link = el("a", { ...attrs, href: `/app/query-report/${encodeURIComponent(report)}` }, content);
	link.addEventListener("click", (event) => {
		if (!is_plain_click(event)) return;
		event.preventDefault();
		frappe.set_route("query-report", report, { ...filters });
	});
	return link;
}

function page_link(page, name, content, attrs = {}) {
	const link = el("a", { ...attrs, href: `/app/${page}/${encodeURIComponent(name)}` }, content);
	link.addEventListener("click", (event) => {
		if (!is_plain_click(event)) return;
		event.preventDefault();
		frappe.set_route(page, name);
	});
	return link;
}

function form_link(doctype, name, content, attrs = {}) {
	const href = `/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}`;
	const link = el("a", { ...attrs, href }, content);
	link.addEventListener("click", (event) => {
		if (!is_plain_click(event)) return;
		event.preventDefault();
		frappe.set_route("Form", doctype, name);
	});
	return link;
}

function is_plain_click(event) {
	return event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey;
}

// Builds DOM from data. Text always goes in through textContent, never as HTML.
function el(tag, attrs = {}, ...children) {
	const node = document.createElement(tag);
	for (const [key, value] of Object.entries(attrs)) {
		if (value === null || value === undefined || value === false) continue;
		if (key === "class") node.className = value;
		else if (key === "text") node.textContent = value;
		else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
		else node.setAttribute(key, value === true ? "" : value);
	}
	for (const child of children.flat(Infinity)) {
		if (child === null || child === undefined || child === false || child === "") continue;
		node.append(child instanceof Node ? child : document.createTextNode(String(child)));
	}
	return node;
}

function icon(name, extra_class = "") {
	const wrapper = document.createElement("span");
	wrapper.className = `ov-icon ${extra_class}`.trim();
	wrapper.setAttribute("aria-hidden", "true");
	// Static markup from ICONS above, never data.
	wrapper.innerHTML = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
	return wrapper;
}

function format_count(value) {
	return format_number(value, null, 0);
}

function format_money(value, currency) {
	// A no-break space, so "₹ 14,67,200" never splits across lines.
	return String(format_currency(value, currency, 0)).replace(/ /g, "\u00a0");
}

// Whole quantities without decimals; fractional ones (2.5 t) keep up to three.
function format_qty(value, uom) {
	const number = format_number(value, null, Number.isInteger(flt(value, 3)) ? 0 : 3);
	return uom ? `${number}\u00a0${uom}` : number;
}

function format_tick(value) {
	return value >= 10000
		? new Intl.NumberFormat(undefined, { notation: "compact" }).format(value)
		: format_count(value);
}

function format_date(value) {
	return moment(value).format("D MMM YYYY");
}

function pretty_date(value) {
	return frappe.datetime.prettyDate(value);
}

function format_time(value) {
	return moment(frappe.datetime.convert_to_user_tz(value)).format("D MMM YYYY, HH:mm");
}
