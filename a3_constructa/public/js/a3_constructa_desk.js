// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

// A new document takes the record you came from. Open a Project, go to (say) the
// BOQ list and press "+ Add BOQ": the new BOQ's Project is that project; the same
// for a quick-entry popup such as a new Task. Only an empty, editable link field
// is filled, and only when exactly one field links to the record's doctype, so
// nothing is guessed. The form then fetches what follows from it as if typed.
frappe.provide("a3_constructa");

a3_constructa.previous_form = function (doctype) {
	const history = frappe.route_history || [];
	// Look a few steps back, past the list (or an earlier new form) of the same doctype.
	for (let i = history.length - 1; i >= Math.max(0, history.length - 4); i--) {
		const route = history[i] || [];
		if (route[1] === doctype && ["List", "Form"].includes(route[0])) continue;
		if (route[0] === "Form" && route[2] && !String(route[2]).startsWith("new-")) {
			return { doctype: route[1], name: route[2] };
		}
		return null;
	}
	return null;
};

const a3_get_new_doc = frappe.model.get_new_doc;
frappe.model.get_new_doc = function (doctype, parent_doc, ...rest) {
	const doc = a3_get_new_doc.call(this, doctype, parent_doc, ...rest);
	if (!parent_doc) {
		try {
			fill_from_previous(doc);
		} catch (e) {
			console.warn("a3_constructa: could not fill from the previous record", e); // never block a new document
		}
	}
	return doc;
};

function fill_from_previous(doc) {
	const meta = frappe.get_meta(doc.doctype);
	if (!meta || meta.istable) return;
	const prev = a3_constructa.previous_form(doc.doctype);
	if (!prev || !frappe.model.can_read(prev.doctype)) return;
	const links = meta.fields.filter(
		(df) => df.fieldtype === "Link" && df.options === prev.doctype && !df.read_only && !df.hidden && !df.is_virtual
	);
	if (links.length !== 1 || doc[links[0].fieldname]) return;
	doc[links[0].fieldname] = prev.name;
	frappe.show_alert({ message: __("{0} set to {1}, the record you came from.", [__(links[0].label), prev.name]), indicator: "blue" });
}

// The checked rows of an estimates import (BOQ and Estimate Sheet), as a preview.
a3_constructa.resources_summary = function (r, currency) {
	if (r.errors.length) {
		return `<div class="alert alert-danger"><b>${__("Nothing imported. Fix these rows and upload again:")}</b><ul>${r.errors
			.map((e) => `<li>${frappe.utils.escape_html(e)}</li>`).join("")}</ul></div>`;
	}
	const rows = Object.entries(r.lines);
	const total = rows.reduce((n, [, l]) => n + l.length, 0);
	return `<p><b>${__("{0} resources for {1} lines ready.", [total, rows.length])}</b>${
		r.replaces.length ? " " + __("{0} of these lines already have resources; theirs will be replaced.", [r.replaces.length]) : ""}</p>
		<div class="table-responsive"><table class="table table-bordered table-sm"><thead><tr><th>${__("Line")}</th><th>${__("Type")}</th><th>${__("Item / description")}</th>
		<th class="text-right">${__("Qty / unit")}</th><th class="text-right">${__("Output / day")}</th><th class="text-right">${__("Rate")}</th></tr></thead><tbody>${rows
			.map(([line, list]) => list.map((x, i) => `<tr><td>${i ? "" : frappe.utils.escape_html(r.refs[line])}</td><td>${__(x.resource_type)}</td>
				<td>${frappe.utils.escape_html(x.item_code ? `${x.item_code}: ${x.description}` : x.description)}</td>
				<td class="text-right">${x.qty_per_unit || ""}${x.wastage_percent ? ` (+${x.wastage_percent}%)` : ""}</td>
				<td class="text-right">${x.output_per_day || ""}</td>
				<td class="text-right">${x.rate ? format_currency(x.rate, currency) : `<span class="text-muted">${__("fetched")}</span>`}</td></tr>`).join(""))
			.join("")}</tbody></table></div>`;
};

// A report opened from a link (filters in the URL) ran before Frappe had checked a
// Link filter's value, so it showed every project under "Mbandaka Administrative
// Centre". Once the filters have settled, run it again if they differ from what it
// ran with.
const a3_report = frappe.views && frappe.views.QueryReport && frappe.views.QueryReport.prototype;
if (a3_report) {
	const run = a3_report.refresh;
	a3_report.refresh = function (...args) {
		this._a3_ran_with = JSON.stringify(this.get_filter_values());
		// Frappe resolves this once the run is drawn; a second run must not start before.
		this._a3_running = Promise.resolve(run.apply(this, args));
		return this._a3_running;
	};
	const open = a3_report.refresh_report;
	a3_report.refresh_report = function (route_options) {
		const from_link = route_options && Object.keys(route_options).length;
		return Promise.resolve(open.apply(this, arguments)).then(() => {
			if (!from_link) return;
			const settle = (tries) =>
				Promise.resolve(this._a3_running).then(() => setTimeout(() => {
					if (JSON.stringify(this.get_filter_values()) !== this._a3_ran_with) this.refresh();
					else if (tries) settle(tries - 1);
				}, 1200)); // after the chart has finished drawing (Frappe animates it)
			settle(3);
		});
	};
}
