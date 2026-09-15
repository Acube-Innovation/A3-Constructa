# A3 Constructa

Construction ERP extensions for ERPNext v15.

## Running it locally

Docker Desktop is the only prerequisite. From this folder:

```powershell
copy .env.example .env      # then edit the two passwords
docker compose up -d
docker compose logs -f backend
```

The first start clones Frappe and ERPNext, creates the site, runs the ERPNext
setup wizard and builds assets — allow 15–30 minutes and watch the `backend`
log. Every later start skips straight to the server.

Then open <http://constructa.localhost:8092/> and sign in as `Administrator`
with the `ADMIN_PASSWORD` from `.env`.

| | |
|---|---|
| Site | `constructa.localhost` |
| Browser | <http://constructa.localhost:8092/> |
| Dev server, bypassing nginx | <http://127.0.0.1:8003/> |
| MariaDB, for a GUI client | `127.0.0.1:3309` |

These ports deliberately avoid the other benches on this machine — a3-optics
(80/8000/3306), a3-retail (8090/8001/3307), a3-loan (8091/8002/3308) and
erpnext15 (8010). Each of those is a separate bench with its own database;
nothing is shared with this one.

## Everyday commands

```powershell
docker compose exec backend bench --site constructa.localhost migrate
docker compose exec backend bench --site constructa.localhost console
docker compose exec backend bench --site constructa.localhost clear-cache
docker compose exec backend bash          # a shell in the bench
```

`docker compose down` stops everything and keeps the data. `down -v` would
delete the bench, the sites and the database — don't.

## How the app gets into the bench

This repository is bind-mounted at `/workspace/a3_constructa` and soft-linked
into the bench as `apps/a3_constructa`. A file edited in Windows is the file the
server runs, and the dev server reloads on Python changes.

## Keeping work in the repository, not in the database

Anything built through the UI is only a row in this site's database until it is
exported. Fixture doctypes are declared in
[`a3_constructa/hooks.py`](a3_constructa/hooks.py); after creating records
through the desk:

```powershell
docker compose exec backend bench export-fixtures --app a3_constructa
```

DocTypes export themselves to source automatically while `developer_mode` is on
(the bootstrap sets it). For a single record, use
`bench --site constructa.localhost export-doc <doctype> <name>`.

Baseline records that need logic rather than a fixture belong in
[`a3_constructa/setup/install_defaults.py`](a3_constructa/setup/install_defaults.py),
which runs on install and on every migrate and is written to be idempotent.

## License

MIT — see [`license.txt`](license.txt). Copyright (c) 2026 Acube Innovations
Pvt Ltd.
