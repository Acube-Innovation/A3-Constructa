#!/usr/bin/env bash
# Entrypoint for the `backend` service: make sure the bench is ready, then be
# the web server. The bootstrap is idempotent, so this is the whole start-up
# path on the first run and on every restart afterwards.

set -euo pipefail

bash /workspace/a3_constructa/docker/bootstrap.sh

cd /workspace/frappe-bench

# The development server: it serves /assets and /files itself and reloads when
# a Python file under apps/ changes — which, for this app, means a file changed
# on the Windows side.
exec bench serve --port 8000
