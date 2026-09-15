#!/usr/bin/env bash
# A3 Constructa — one-time (and idempotent) preparation of the bench inside
# Docker.
#
# Runs automatically the first time the `backend` service starts, and can be
# re-run at any time:
#
#     docker compose exec backend /workspace/a3_constructa/docker/bootstrap.sh
#
# Every step is guarded, so re-running it neither reinstalls an app nor touches
# an existing site or database.

set -euo pipefail

BENCH_DIR=/workspace/frappe-bench
APP_SRC=/workspace/a3_constructa
SITE="${SITE_NAME:-constructa.localhost}"
STAMP="$BENCH_DIR/.a3-bootstrap-complete"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

wait_for() {
	local host=$1 port=$2
	printf 'waiting for %s:%s ' "$host" "$port"
	for _ in $(seq 1 150); do
		if nc -z "$host" "$port" 2>/dev/null; then echo "ok"; return 0; fi
		printf '.'
		sleep 2
	done
	echo
	echo "timed out waiting for $host:$port" >&2
	return 1
}

wait_for mariadb 3306
wait_for redis-cache 6379
wait_for redis-queue 6379

# ---------------------------------------------------------------- the bench
if [ ! -d "$BENCH_DIR/apps/frappe" ]; then
	log "Initialising the bench — frappe ${FRAPPE_BRANCH}, python ${PYENV_VERSION}"
	cd /workspace
	# --ignore-exist: the directory is a mount point and therefore already
	#   there. --skip-redis-config-generation: redis is two containers, not
	#   local processes. --skip-assets: everything is built once, at the end,
	#   rather than after each app.
	bench init \
		--ignore-exist \
		--skip-redis-config-generation \
		--skip-assets \
		--frappe-branch "${FRAPPE_BRANCH}" \
		--python "$(pyenv prefix "${PYENV_VERSION}")/bin/python" \
		--verbose \
		frappe-bench
fi

cd "$BENCH_DIR"

log "Pointing the bench at the Docker services"
bench set-config -g db_host mariadb
bench set-config -gp db_port 3306
bench set-config -g redis_cache "redis://redis-cache:6379"
bench set-config -g redis_queue "redis://redis-queue:6379"
bench set-config -g redis_socketio "redis://redis-queue:6379"
bench set-config -gp socketio_port 9000
bench set-config -gp developer_mode 1
# The dev server is the only thing serving this bench; let it answer for the
# site whose name arrives in the Host header.
bench set-config -gp serve_default_site 1 || true

# ------------------------------------------------------------------- apps
fetch_app() {
	local name=$1 url=$2 branch=$3
	if [ -d "$BENCH_DIR/apps/$name" ]; then
		echo "$name already in the bench"
		return 0
	fi
	log "Fetching $name ($branch)"
	bench get-app --skip-assets --branch "$branch" "$name" "$url"
}

fetch_app erpnext https://github.com/frappe/erpnext "${ERPNEXT_BRANCH}"

# This app is not cloned — it is the repository on the Windows side, mounted in
# and soft-linked, so an edit in the editor is an edit in the bench.
if [ ! -e "$BENCH_DIR/apps/a3_constructa" ]; then
	log "Linking a3_constructa from the mounted repository"
	bench get-app --skip-assets --soft-link "$APP_SRC"
fi

# ------------------------------------------------------------------- site
if [ ! -d "$BENCH_DIR/sites/$SITE" ]; then
	log "Creating the site $SITE"

	# The database user a site gets must be allowed in from another container,
	# not just from localhost. Newer bench spells that as a login scope; older
	# bench as --no-mariadb-socket.
	scope_flag=()
	if bench new-site --help 2>&1 | grep -q -- '--mariadb-user-host-login-scope'; then
		scope_flag=(--mariadb-user-host-login-scope='%')
	elif bench new-site --help 2>&1 | grep -q -- '--no-mariadb-socket'; then
		scope_flag=(--no-mariadb-socket)
	fi

	bench new-site "$SITE" \
		--db-root-username root \
		--db-root-password "${MARIADB_ROOT_PASSWORD}" \
		--admin-password "${ADMIN_PASSWORD}" \
		"${scope_flag[@]}" \
		--verbose

	bench use "$SITE"
fi

installed_apps() { bench --site "$SITE" list-apps 2>/dev/null | awk '{print $1}'; }

install_app() {
	local app=$1
	if installed_apps | grep -qx "$app"; then
		echo "$app already installed on $SITE"
	else
		log "Installing $app on $SITE"
		bench --site "$SITE" install-app "$app"
	fi
}

install_app erpnext

# A site with ERPNext installed but no Company is still an empty shell: the
# masters everything else builds on — UOM "Nos", the item groups, the price
# lists, a fiscal year — are created by the setup wizard, not by the install.
# This is development-environment data, not app data.
has_company() {
	# `bench execute` prints a returned value and nothing at all for None, so
	# output here means a Company exists.
	bench --site "$SITE" execute frappe.db.get_value \
		--kwargs "{'doctype': 'Company', 'filters': {}, 'fieldname': 'name'}" 2>/dev/null \
		| grep -q '[A-Za-z0-9]'
}

if [ "${SETUP_WIZARD:-1}" = "1" ] && ! has_company; then
	if [ "$(date +%m)" -ge 4 ]; then
		FY_START="$(date +%Y)-04-01"
		FY_END="$(( $(date +%Y) + 1 ))-03-31"
	else
		FY_START="$(( $(date +%Y) - 1 ))-04-01"
		FY_END="$(date +%Y)-03-31"
	fi

	log "Running the ERPNext setup wizard — ${COMPANY_NAME} (${COUNTRY}), FY ${FY_START}"
	bench --site "$SITE" execute \
		frappe.desk.page.setup_wizard.setup_wizard.setup_complete \
		--kwargs "{'args': {
			'language': 'English',
			'country': '${COUNTRY}',
			'timezone': '${TIMEZONE}',
			'currency': '${CURRENCY}',
			'company_name': '${COMPANY_NAME}',
			'company_abbr': '${COMPANY_ABBR}',
			'chart_of_accounts': 'Standard',
			'domain': 'Services',
			'bank_account': 'Cash',
			'fy_start_date': '${FY_START}',
			'fy_end_date': '${FY_END}',
			'full_name': 'Administrator',
			'email': 'admin@example.com'
		}}"
fi

# This app's installer seeds records that hang off ERPNext masters, so it goes
# in after the wizard.
install_app a3_constructa

log "Site settings for development"
bench --site "$SITE" set-config -p developer_mode 1
# `bench run-tests` refuses to touch a site that has not opted in.
bench --site "$SITE" set-config allow_tests true
bench --site "$SITE" enable-scheduler || true
bench use "$SITE"

# ------------------------------------------------------- assets and schema
if [ ! -f "$STAMP" ]; then
	log "Installing node dependencies and building assets (first run only)"
	bench setup requirements --node
	bench build
fi

log "Running migrations"
bench --site "$SITE" migrate
bench --site "$SITE" clear-cache

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$STAMP"
log "Bench ready — site $SITE"
