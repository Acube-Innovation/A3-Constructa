// Copyright (c) 2026, Acube Innovations Pvt Ltd and contributors
// For license information, please see license.txt

const LOOKAHEAD = "a3_constructa.a3_constructa.report.three_week_look_ahead.three_week_look_ahead";
const CHECKS = ["material", "crew_check", "equipment", "permit", "drawings", "predecessors"];

frappe.query_reports["Three-Week Look-Ahead"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "wbs", label: __("WBS"), fieldtype: "Link", options: "WBS",
			get_query: () => {
				const project = frappe.query_report.get_filter_value("project");
				return project ? { filters: { project } } : {};
			},
		},
		{ fieldname: "crew", label: __("Crew"), fieldtype: "Link", options: "Crew" },
	],
	onload(report) {
		report.page.add_inner_button(__("Commit week"), () => {
			frappe.confirm(
				__("Commit the Ready tasks starting next week? Their Committed Week is set to next Monday, and next week's PPC counts them."),
				() => frappe.call({
					method: `${LOOKAHEAD}.commit_week`,
					args: { filters: report.get_filter_values() },
					freeze: true,
				}).then(({ message: r }) => {
					const week = frappe.datetime.str_to_user(r.week);
					const lines = [];
					if (r.committed.length) lines.push(__("Committed for the week of {0}: {1}.", [week, r.committed.join(", ")]));
					if (r.already.length) lines.push(__("Already committed: {0}.", [r.already.join(", ")]));
					if (r.not_ready.length) lines.push(__("Not ready, so not committed: {0}.", [r.not_ready.join(", ")]));
					if (!lines.length) lines.push(__("No tasks start in the week of {0}.", [week]));
					frappe.msgprint({ title: __("Commit week"), message: lines.join("<br>"), indicator: r.committed.length ? "green" : "blue" });
					report.refresh();
				})
			);
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "ready") {
			const ok = data.blockers === 0;
			return `<span class="indicator-pill ${ok ? "green" : "red"}">${value}</span>`;
		}
		if (CHECKS.includes(column.fieldname)) {
			const raw = data[column.fieldname] || "";
			if (raw === "OK") return `<span class="text-success">${value}</span>`;
			if (raw === "—" || raw.startsWith("Not checked")) return `<span class="text-muted">${value}</span>`;
			return `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
