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
	]]]},
	# Only the records this app introduces. "Approved", "Rejected", "Approve"
	# and "Reject" ship with Frappe and must not be re-exported as ours.
	{"dt": "Workflow", "filters": [["name", "in", ["BOQ Approval"]]]},
	{"dt": "Workflow State", "filters": [["name", "in", ["Draft", "Pending Approval"]]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", ["Submit for Approval"]]]},
]

# Naming series are not a doctype of their own: `bench setup naming-series` and
# the Document Naming Rule UI both write to the `options` of the target
# doctype's `naming_series` field, which is stored as a Property Setter — and
# Property Setter is already exported above. Series that need a rule rather than
# a field option are Document Naming Rule records; add that doctype to the list
# above when Phase 2 introduces one.

# ---------------------------------------------------------------- assets
# app_include_css = "/assets/a3_constructa/css/a3_constructa_desk.css"
# app_include_js = "/assets/a3_constructa/js/a3_constructa_desk.js"

# ---------------------------------------------------------------- events
# Build sheet head 48 row 19: a material issue must post to the project GL head
# its Cost Code names, not the item or company default.
doc_events = {
	"Stock Entry": {
		# before_naming runs inside set_new_name, before the series is consumed.
		"before_naming": "a3_constructa.overrides.stock_entry.set_naming_series",
		"validate": "a3_constructa.overrides.stock_entry.set_cost_code_accounting",
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
}

# scheduler_events = {}
