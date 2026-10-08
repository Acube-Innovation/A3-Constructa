app_name = "a3_constructa"
app_title = "A3 Constructa"
app_publisher = "Acube Innovations Pvt Ltd"
app_description = "Construction ERP extensions for ERPNext"
app_email = "saaspurchases@acube.co"
app_license = "mit"

# ERPNext supplies the Project, Item, Asset, Stock and Accounts doctypes this
# app extends; without it, installing here is meaningless.
required_apps = ["frappe/erpnext", "hrms"]

# Everything this app owns lives in one module, matching how the other A3 apps
# are built: a single `Module = A3 Constructa` filter then lists every DocType,
# Report and Workspace the app adds. Workspaces still carry their own titles
# (including the ampersand in "Planning & Budgeting"), which is what the desk
# sidebar shows.
A3_CONSTRUCTA_MODULES = ["A3 Constructa"]


# ---------------------------------------------------------------- install
before_install = "a3_constructa.install.before_install"
after_install = "a3_constructa.install.after_install"
after_migrate = "a3_constructa.install.after_migrate"
before_tests = "a3_constructa.install.before_tests"

# ---------------------------------------------------------------- fixtures
#
# Anything built through the UI — a custom field, a workflow, a workspace, a
# naming series — is otherwise only a row in this site's database. Listing the
# doctype here makes `bench export-fixtures --app a3_constructa` write it to
# a3_constructa/fixtures/*.json, where it is version-controlled and reinstalled
# automatically on `bench migrate` of any other site.
#
# The filters matter as much as the list. Custom Field, Property Setter and
# Workspace carry a `module`, so they are scoped to this app's module — set the
# module when creating them in Customize Form, or they will not be exported.
#
# The master-data doctypes below (Item Group, Stock Entry Type, Warehouse Type,
# Workflow and friends) have no `module` field, so there is nothing to scope
# them by except their names. Each is pinned to an explicit allow-list: an
# unfiltered entry would export every stock ERPNext Item Group into this app and
# reinstall them onto every other site. Add a name here whenever a record is
# created - between them these lists are the app's inventory of the master data
# it owns, and a record missing from them is a record that will not exist on a
# fresh install.
fixtures = [
	# Fixture import runs after the module sync on every `bench migrate`, so for
	# these doctypes the exported JSON - not the database - is the source of
	# truth. If you ever change the module of a record listed here, re-export
	# before migrating: a stale export silently reverts the change, and records
	# the filter no longer matches drop out of version control entirely.
	{"dt": "Custom Field", "filters": [["module", "in", A3_CONSTRUCTA_MODULES]]},
	{"dt": "Property Setter", "filters": [["module", "in", A3_CONSTRUCTA_MODULES]]},
	# Workspace is deliberately NOT a fixture. A Workspace with a module is
	# already exported to that module's folder and synced by `bench migrate`;
	# listing it here too gave it two sources of truth, and the fixture - which
	# imports after the module sync - silently overwrote the module copy,
	# wiping parent_page and un-nesting the sidebar.
	# Build sheet heads 31-37. "Services" is an ERPNext record this app converts
	# to a group so Transport, Installation and Testing & Commissioning can hang
	# off it; exporting it here is what reproduces that conversion elsewhere.
	{"dt": "Item Group", "filters": [["name", "in", [
		"Construction Materials", "Consumables",
		"Services", "Transport", "Installation", "Testing & Commissioning",
		"Subcontract Works", "Spare Parts", "Small Tools",
		"Rental Equipment", "Temporary Works",
	]]]},
	# Asset Category is deliberately NOT a fixture: its `accounts` child table is
	# mandatory and company-specific, so an exported copy would carry this site's
	# company and chart of accounts. Built in setup/install_defaults.py instead.
	# Build sheet heads 43, 46 and 48 - the issue, receipt and return note types.
	{"dt": "Stock Entry Type", "filters": [["name", "in", [
		"Material Issue Note (MIN)", "Material Receipt Note (MRN)",
		"Site Material Return",
		# heads 55 - the small-tools custody cycle
		"Tool Issue", "Tool Return", "Tool Write-off",
	]]]},
	# Head 47 row 16 filters site stores on this warehouse type. "Transit"
	# (head 44) already ships with ERPNext and is deliberately not re-exported.
	{"dt": "Warehouse Type", "filters": [["name", "in", ["Site", "Custody"]]]},
	# Build sheet head 40 row 19 - the documents an import shipment carries.
	{"dt": "Document Type", "filters": [["name", "in", [
		"Certificate of Origin", "CNF Invoice",
		"Duty Payment Receipt", "Delivery Order",
		# Catalogue 9.6: what a subcontractor must hold before a Work Certificate is submitted.
		"Insurance Certificate", "Labour Compliance Certificate", "Tax Clearance Certificate",
	]]]},
	# Only the records this app introduces. "Approved", "Rejected", "Approve"
	# and "Reject" ship with Frappe and must not be re-exported as ours.
	# States and actions first: fixtures import in this order, and a workflow's
	# rows link to its states and actions.
	{"dt": "Workflow State", "filters": [["name", "in", [
		"Draft", "Pending Approval", "Pending Management Approval", "Submitted", "Cancelled",
		# Catalogue 2.2: the bid / no-bid decision on an opportunity.
		"Scoring", "Awaiting Bid Decision", "Go", "No-go",
	]]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", [
		"Submit for Approval", "Submit", "Send for Decision", "Confirm Go", "Confirm No-go", "Send Back", "Reopen",
	]]]},
	{"dt": "Workflow", "filters": [["name", "in", ["BOQ Approval", "Quotation Margin Approval", "Bid Decision"]]]},
]

# Naming series are not a doctype of their own: `bench setup naming-series` and
# the Document Naming Rule UI both write to the `options` of the target
# doctype's `naming_series` field, which is stored as a Property Setter — and
# Property Setter is already exported above. Series that need a rule rather than
# a field option are Document Naming Rule records; add that doctype to the list
# above when Phase 2 introduces one.

# ---------------------------------------------------------------- assets
# app_include_css = "/assets/a3_constructa/css/a3_constructa_desk.css"
app_include_js = "/assets/a3_constructa/js/a3_constructa_desk.js"

# Material Request gains Get Items From > BOQ.
doctype_js = {
	"Task": "public/js/task.js",
	"Material Request": ["public/js/material_request.js", "public/js/approvals.js"],
	"Purchase Order": "public/js/approvals.js",
	"Opportunity": "public/js/opportunity.js",
	"Quotation": "public/js/quotation.js",
	"Sales Order": "public/js/sales_order.js",
	"Project": "public/js/project.js",
}

# ---------------------------------------------------------------- events
ACTIVE_WBS = "a3_constructa.overrides.wbs_posting.validate_active_wbs"
ACTIVE_COST_CODE = "a3_constructa.overrides.cost_code_accounting.validate_active_cost_codes"
COST_CODE_ACCOUNTING = "a3_constructa.overrides.cost_code_accounting.apply_cost_code_accounting"
# Catalogue 9.3, 14.2: approval levels from the Approval Matrix, then the budget check.
APPROVAL_LEVEL = "a3_constructa.overrides.approvals.set_required_level"
APPROVAL_GATE = [
	"a3_constructa.overrides.approvals.check_levels_before_submit",
	"a3_constructa.overrides.approvals.check_budget",
]

# Build sheet head 48 row 19: a material issue must post to the project GL head
# its Cost Code names, not the item or company default.
# Catalogue 6.1-6.2: linked tasks reschedule by type and lag (ERPNext's own knows
# finish-to-start only, and would push a start-to-start successor wrongly).
override_doctype_class = {
	"Task": "a3_constructa.overrides.task.ConstructaTask",
}

doc_events = {
	"Task": {
		"validate": ["a3_constructa.overrides.task.validate", "a3_constructa.overrides.task_resources.validate",
		             "a3_constructa.overrides.task_baseline.validate", "a3_constructa.overrides.task_progress.validate"],
		"on_update": ["a3_constructa.overrides.task.on_update", "a3_constructa.overrides.task_progress.on_update",
		              "a3_constructa.a3_constructa.doctype.procurement_plan.procurement_plan.on_task_update"],
		"after_delete": "a3_constructa.overrides.task.after_delete",
	},
	"Stock Entry": {
		# before_naming runs inside set_new_name, before the series is consumed.
		"before_naming": "a3_constructa.overrides.stock_entry.set_naming_series",
		"validate": [
			"a3_constructa.overrides.stock_entry.set_cost_code_accounting",
			ACTIVE_WBS,
			ACTIVE_COST_CODE,
			"a3_constructa.overrides.fuel.validate",
		],
		# Catalogue 8.4: fuel issued to a machine shows on its Equipment Log.
		"on_submit": "a3_constructa.overrides.fuel.update_logs",
		"on_cancel": "a3_constructa.overrides.fuel.update_logs",
	},
	"Asset": {
		# Head 51 row 2: number an asset from its category, not one shared series.
		"before_naming": "a3_constructa.overrides.asset.set_naming_series_from_category",
	},
	"Serial No": {
		# Head 55 row 23 filters the tool register by item group, which ERPNext
		# leaves empty on every serial it creates.
		"before_insert": "a3_constructa.overrides.serial_no.set_item_group",
	},
	# A request line fetched from a BOQ must still match its BOQ line; warn when
	# the requests for a line add up to more than it approved.
	"Material Request": {
		"validate": [
			"a3_constructa.overrides.material_request.validate_boq_lines",
			ACTIVE_WBS,
			ACTIVE_COST_CODE,
			APPROVAL_LEVEL,
		],
		"before_submit": APPROVAL_GATE,
		# Catalogue 5.4: the procurement plan's lines follow what has been requested.
		"on_update": "a3_constructa.a3_constructa.doctype.procurement_plan.procurement_plan.on_request_change",
		"on_cancel": "a3_constructa.a3_constructa.doctype.procurement_plan.procurement_plan.on_request_change",
		"on_trash": "a3_constructa.a3_constructa.doctype.procurement_plan.procurement_plan.on_request_change",
	},
	# Catalogue 1.2: only an Active WBS node accepts postings. Catalogue 1.3:
	# only an Active cost code can be used.
	"Purchase Order": {"validate": [ACTIVE_WBS, ACTIVE_COST_CODE, APPROVAL_LEVEL], "before_submit": APPROVAL_GATE},
	"Timesheet": {"validate": [ACTIVE_WBS, ACTIVE_COST_CODE]},
	"WBS Allocation": {"validate": [ACTIVE_WBS, ACTIVE_COST_CODE]},
	"Variation Order": {"validate": ACTIVE_WBS},
	"Purchase Receipt": {"validate": ACTIVE_COST_CODE},
	"Request for Quotation": {"validate": ACTIVE_COST_CODE},
	"Supplier Quotation": {"validate": ACTIVE_COST_CODE},
	# Catalogue 4.1: an awarded order carries the contract's terms, a BOQ line and WBS per line.
	"Sales Order": {
		"validate": [ACTIVE_COST_CODE, "a3_constructa.overrides.sales_order.validate"],
		"before_submit": "a3_constructa.overrides.sales_order.before_submit",
	},
	# Catalogue 2.2: the bid / no-bid score and decision.
	"Opportunity": {"validate": "a3_constructa.overrides.opportunity.validate"},
	# Catalogue 2.7: a tender quotation's margin, revisions and margin approval.
	"Quotation": {
		"validate": "a3_constructa.overrides.quotation.validate",
		"before_submit": "a3_constructa.overrides.quotation.check_margin_approval",
		"on_cancel": "a3_constructa.overrides.quotation.set_cancelled_state",
	},
	# Catalogue 4.2: a cancelled or deleted milestone invoice frees its milestone.
	"Sales Invoice": {
		"validate": ACTIVE_COST_CODE,
		"on_cancel": "a3_constructa.api.client_billing.release_links",
		"on_trash": "a3_constructa.api.client_billing.release_links",
	},
	"BOQ": {"validate": ACTIVE_COST_CODE},
	"Budget Transfer": {"validate": ACTIVE_COST_CODE},
	# Catalogue 1.7, 9.9: a line with a cost code posts to the cost code's account
	# and cost centre; invoice lines from an order are checked three ways.
	"Purchase Invoice": {
		"validate": [
			ACTIVE_COST_CODE,
			COST_CODE_ACCOUNTING,
			"a3_constructa.overrides.cost_code_accounting.check_three_way_match",
		],
		# Catalogue 9.6: the invoice of a Work Certificate moves its retention to Retention Payable.
		"on_submit": "a3_constructa.api.subcontract_billing.on_submit",
		"before_cancel": "a3_constructa.api.subcontract_billing.before_cancel",
		"on_cancel": "a3_constructa.api.subcontract_billing.release_links",
		"on_trash": "a3_constructa.api.subcontract_billing.release_links",
	},
	"Journal Entry": {"validate": [ACTIVE_COST_CODE, COST_CODE_ACCOUNTING]},
	# Catalogue 6.8: a site inspection on a task; a rejected one raises an NCR.
	"Quality Inspection": {
		"validate": "a3_constructa.overrides.quality.qi_validate",
		"before_submit": "a3_constructa.overrides.quality.qi_before_submit",
		"on_submit": "a3_constructa.overrides.quality.qi_on_submit",
	},
	"Non Conformance": {"validate": "a3_constructa.overrides.quality.nc_validate"},
	# Catalogue 6.11: a defect in the defects liability period, on the project and WBS.
	"Warranty Claim": {"before_validate": "a3_constructa.overrides.handover.warranty_claim_defaults",
	                   "validate": "a3_constructa.overrides.handover.warranty_claim_validate"},
	"Expense Claim": {"validate": [ACTIVE_COST_CODE, COST_CODE_ACCOUNTING]},
	"Employee": {"validate": "a3_constructa.overrides.certificates.employee_validate"},
}

scheduler_events = {
	# Catalogue 5.4: plan lines pass their PR date overnight.
	"daily": [
		"a3_constructa.a3_constructa.doctype.procurement_plan.procurement_plan.daily",
		# Catalogue 7.7: certificates expiring in 30 and 7 days.
		"a3_constructa.overrides.certificates.daily",
		# Catalogue 13.6: exception alerts.
		"a3_constructa.api.alerts.daily",
	],
}
