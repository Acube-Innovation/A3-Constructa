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

const get_new_doc = frappe.model.get_new_doc;
frappe.model.get_new_doc = function (doctype, parent_doc, ...rest) {
	const doc = get_new_doc.call(this, doctype, parent_doc, ...rest);
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
