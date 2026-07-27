---
name: phantom-dev
description: Use for any phantom-ledger web dev-server lifecycle (start/stop/health-check), QA/browser verification of the FastAPI+HTMX UI, or navigating the web layer (routes/templates). Trigger on tasks involving the dev server, /quick or dashboard pages, Playwright/curl QA checks, or editing src/phantom/web/**.
---

# Phantom Ledger Web Dev

Dense reference for the FastAPI+HTMX web UI so the server, routes, and QA
harness don't get re-derived from scratch each session.

## Dev server: start / stop / health-check

Start (uses existing `start_web.sh`, do not rewrite it):
```bash
./start_web.sh                 # foreground, 127.0.0.1:8000
RELOAD=1 ./start_web.sh &      # background with autoreload, if needed
```
Equivalent direct command (only if you need to bypass the script):
```bash
uv run uvicorn phantom.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

Stop:
```bash
pkill -f "uvicorn phantom.web.app:create_app" || true
# or, if you started it with & and captured $!:
kill %1
```

Health check (don't guess — one-liner, no scripts needed):
```bash
curl -sf http://127.0.0.1:8000/ -o /dev/null && echo UP || echo DOWN
```
If `curl` fails, check for a stray process first:
```bash
pgrep -fal "uvicorn phantom.web.app:create_app"
```

There is no `stop_web.sh` in the repo — the `pkill` one-liner above is the
canonical way to stop it. If you add a stop script, keep it beside
`start_web.sh` and update this section.

## Web layer map

App factory: `src/phantom/web/app.py` — `create_app()` builds the FastAPI
app, mounts `static/`, sets up Jinja2 `templates` (dir:
`src/phantom/web/templates/`), and calls `include_router()` for each router
below, in this order:

| Router file | Router var | Included in app.py |
|---|---|---|
| `routes/dashboard.py` | `dashboard.router` | line 39 |
| `routes/clock.py` | `clock.router` | line 40 |
| `routes/positions.py` | `positions.router` | line 41 |
| `routes/orders.py` | `orders.router` | line 42 |
| `routes/brokers.py` | `brokers.router` | line 43 |
| `routes/simulation.py` | `simulation.router` | line 44 |
| `routes/quick.py` | `quick.router` | line 45 |
| `routes/api.py` | `api_routes.router` | line 46 |

### Routes → templates

- `routes/dashboard.py`
  - `GET /` → `dashboard.html`
- `routes/clock.py`
  - `GET /api/clock` → `_clock_panel.html`
  - `POST /clock/set`, `POST /clock/step` (no template, HTMX triggers refresh)
- `routes/positions.py`
  - `GET /positions/{position_id}` → `position_detail.html`
  - `POST /positions/{position_id}/close`
  - `POST /positions/{position_id}/notes`, `POST /positions/{position_id}/notes/{note_id}/delete`
- `routes/orders.py`
  - `GET /orders` → `order_history.html`
  - `GET /orders/new`, `POST /orders/new` → `order_form.html` (success → `order_confirmation.html`)
  - `POST /orders/{order_id}/cancel`, `/fill`, `/modify`
- `routes/brokers.py`
  - `GET /brokers/compare` → `broker_comparison.html`
- `routes/simulation.py`
  - `POST /simulation/run` (no template)
- `routes/quick.py` (the busiest page — `/quick` is a single-page HTMX-heavy blotter)
  - `GET /quick` → `quick.html`
  - `GET /api/quick/rows` → `_quick_rows.html` (HTMX partial refresh of the row table)
  - `POST /api/quick/rebuild-equity`, `GET /api/quick/equity-data` (equity chart data, no template)
  - `PUT /api/quick/row/{order_id}`, `DELETE /api/quick/row/{order_id}`, `POST /api/quick/order` → all return `_quick_rows.html`
- `routes/api.py` (shared HTMX partial endpoints, used by dashboard + others)
  - `GET /api/equity-snapshot` → `_equity_panel.html`
  - `GET /api/positions-rows` → `_positions_rows.html`
  - `GET /api/orders-rows` → `_orders_rows.html`
  - `GET /api/price` (HTML fragment), `GET /api/equity-data` (JSON)

Templates directory also has `base.html` (shared layout, all full pages
extend it). Partial templates are prefixed with `_`.

### File → responsibility (for targeted reads, not full-file reads)

- `app.py` — factory, router wiring, template/static config. ~46 lines relevant.
- `routes/quick.py` — largest route file (~700+ lines); grep for the specific
  `@router` path you need instead of reading top-to-bottom.
- `routes/api.py` — small HTMX partial endpoints shared across pages.
- `templates/dashboard.html`, `templates/quick.html` — full-page shells;
  the interesting HTMX wiring (`hx-get`, `hx-trigger`, `hx-target`) is usually
  near the top of the `<body>` or in the relevant `_*.html` partial.

## QA verification

### Preferred: Playwright snapshot harness

Use `scripts/qa_snapshot.py` instead of writing new Playwright boilerplate.
It navigates, waits for `networkidle`, captures console errors / page errors
/ failed HTTP requests, and screenshots — exit code is non-zero if anything
was captured.

```bash
uv run python scripts/qa_snapshot.py /quick --out /tmp/quick.png
uv run python scripts/qa_snapshot.py /positions/<id> --out /tmp/pos.png --full-page
uv run python scripts/qa_snapshot.py http://127.0.0.1:8000/orders
```
Flags: `--out PATH` (screenshot path), `--full-page`, `--timeout MS`.
Requires the dev server already running (see above) and Playwright browsers
installed (`uv run playwright install chromium` if missing).

### Fallback: curl one-liner (no browser, fast smoke test)

For a quick "does this endpoint render / contain expected text" check
without spinning up Playwright:
```bash
curl -s http://127.0.0.1:8000/quick | grep -o '<table[^>]*>' 
curl -s http://127.0.0.1:8000/api/quick/rows | grep -c '<tr'
```
Use this for HTMX partial endpoints (`/api/...`) where you just need to
confirm status/shape, not visual rendering. Use the Playwright script when
JS behavior, console errors, or layout matters.

## Notes

- `PHANTOM_DATA` env var controls the data dir (default `./data`); the web
  UI reads/writes through the same `phantom` library API as the CLI.
- Router order in `app.py` matters for path matching if routes ever overlap;
  currently they don't (no ambiguous prefixes).
