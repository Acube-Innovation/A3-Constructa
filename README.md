# A3 Constructa

Construction ERP extensions for ERPNext v15.

## Picking up where you left off

Everything is already built and the demo data is loaded. On a normal day there
is nothing to set up:

1. **Start Docker Desktop** and wait for the whale icon to stop animating.
2. Give it **two to three minutes**. The containers carry `restart:
   unless-stopped`, so they come back on their own.
3. Open <http://localhost:8092/> and sign in as `Administrator` / the
   `ADMIN_PASSWORD` in `.env`.

That is the whole routine. Nothing is lost when the machine shuts down: the
bench, the site database and all the demo records live in Docker volumes, not
in the containers.

If the page does not load after a few minutes, or you stopped the stack by
hand, start it explicitly from this folder:

```powershell
docker compose up -d          # ~2 minutes from cold
docker compose ps             # all eight should say "running"
docker compose logs -f backend
```

Four other benches on this machine (a3-optics, a3-retail, a3-loan, erpnext15)
start at the same time and compete for memory. If things feel slow, stop the
ones you are not using — `docker compose down` in their own folders — rather
than stopping Docker altogether.

| Check | Command |
|---|---|
| Is it up? | `curl http://127.0.0.1:8092/api/method/ping` → `{"message":"pong"}` |
| Something looks stale | `docker compose exec backend bench --site constructa.localhost clear-cache` |
| After pulling new code | `docker compose exec backend bench --site constructa.localhost migrate` |

## First-time setup

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
