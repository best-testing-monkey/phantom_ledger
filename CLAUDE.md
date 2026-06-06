# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Phantom Ledger is a local-first Python paper trading and backtesting engine. It is both a library (`from phantom import Phantom`) and a CLI tool (`phantom order place ...`). The CLI is a thin wrapper around the library API — no business logic lives in the CLI.

The full architecture spec is in `phantom-ledger-architecture.md`. Read it before starting any implementation work.

## Commands

```bash
# Install dependencies (uses uv)
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/unit/test_commission.py

# Run with coverage
uv run pytest --cov=src/phantom

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Install the CLI in development mode
uv run phantom --help
```

The `PHANTOM_DATA` env var controls the data directory (default: `./data`).

## Architecture

```
src/phantom/
  __init__.py          # Public re-exports (Phantom, Account, Order, etc.)
  cli.py               # Typer CLI — thin wrapper, no logic
  api/                 # Public API: Phantom facade + sub-APIs (accounts, orders, positions, etc.)
  models/              # Pydantic domain models + types.py (Literal type aliases)
  engine/              # Simulation loop, order/position/margin managers, clock abstraction
  costs/               # Cost sub-models: commission, spread, slippage, overnight, fx, dividend
  data/                # DataProvider protocol + price_cache( git@github.com:best-testing-monkey/price_cache.git )/Alpaca adapters 
  db/                  # SQLite connection, migration runner, repositories (one per entity)
  profiles/            # BrokerProfile JSON loader + bundled broker JSON files
  notes/               # Filesystem-backed trade note CRUD
  reports/             # Metrics, equity curves, cost comparisons, formatters
  alerts/              # (Phase 3) Telegram/Discord dispatchers
  errors.py            # PhantomError hierarchy
  config.py            # App-wide settings, env loading, path resolution
```

### Key Abstractions

**Clock protocol** — lets the same engine run in backtest and live paper-trade mode without branching. `BacktestClock` steps through a `DatetimeIndex`; `LiveClock` blocks until next wall-clock tick.

**DataProvider protocol** — abstracts price/dividend source. `HistoricalProvider` reads from price_cache submodule ( git@github.com:best-testing-monkey/price_cache.git ). `LiveProvider` reads Yahoo/Alpaca live feed.

**CostEngine** — single entry point that composes all cost sub-models from a `BrokerProfile`. Called on every fill. Returns a `CostBreakdown` dataclass.

**Phantom facade** — top-level object created by the user (`ph = Phantom(data_dir="./data")`). Exposes sub-APIs as attributes (`ph.accounts`, `ph.orders`, `ph.positions`, etc.). No global state; multiple instances can coexist.

### Layering Rules

- **External consumers** depend only on `phantom` (the public API) and `phantom.errors`. Never on `phantom.db`, `phantom.engine`, etc.
- **CLI module** imports only `phantom` and `phantom.errors`.
- **Integration tests** exercise the public API only.
- **API layer** is the transaction boundary for multi-step operations — one commit per API call.
- **Repos** handle all DB I/O; API layer handles validation and orchestration.

## Implementation Standards

These apply to every module. See `phantom-ledger-architecture.md` Appendix A for full details.

### IDs
Use ULIDs via `phantom.utils.ids.new_id()`. Assigned in Python at creation time, never by the DB.

### Datetimes
All datetimes are timezone-aware UTC internally. Use `parse_datetime()`, `now_utc()`, `to_iso()` from `phantom.utils.datetime`. Store as ISO 8601 TEXT in SQLite. Accept `str | datetime` at API boundaries.

### Models
Pydantic v2 `BaseModel`. Use `Literal` type aliases from `phantom.models.types` for constrained fields (not Python `Enum`). Use `frozen=True` only for value objects like `CostBreakdown`.

### Exceptions
Always raise specific subclasses: `NotFoundError`, `InsufficientFundsError`, `MarginError`, `ValidationError`, `DataError`, `ProfileError`. Never raise bare `PhantomError`. `get()` methods raise `NotFoundError` on miss — never return `None`. `list()` methods return empty list on no matches.

### Repos
Constructor-injected `sqlite3.Connection`. Standardized methods: `create()`, `get()`, `get_by_name()`, `list()`, `update()`, `delete()`. All writes call `self._conn.commit()`. Use `sqlite3.Row` row factory.

### SQL
Parameterized queries only (`?` placeholders). `PRAGMA foreign_keys = ON` on every connection. SQLite WAL mode.

### CLI
Every command: `try` → `get_phantom()` → call API → format with Rich → `except PhantomError` → `console.print(f"[red]Error:[/red] {e}")` + `raise typer.Exit(code=1)`. Destructive commands require `typer.confirm()` unless `--yes` flag.

### Tests
- Unit tests: pure function verification, exact equality for deterministic math, `pytest.approx()` only for expected float accumulation.
- Integration tests: use `phantom_instance` fixture (in-memory SQLite), exercise public API only, mock only external HTTP (price_cache, central bank APIs).
- Never mock the database.

### Logging
`logger = logging.getLogger(__name__)`. Use `%s` formatting (not f-strings). Levels: DEBUG=per-bar loop detail, INFO=fills/closes/margin calls, WARNING=degraded state, ERROR=non-fatal failures.

### Imports
Always absolute (`from phantom.models.account import Account`). Never relative. Groups: stdlib → third-party → internal, separated by blank lines.

## Build Order (MVP)

E1 Scaffolding → E2 Broker Profiles → E3 Cost Engine (MVP) → E4 Data Layer → E5 Accounts → E6 Orders → E7 Positions → E9 Simulation Engine → E10 Replay → E11 Notes → E12 Reporting → E17 Library API surface + CLI wiring

See `phantom-ledger-architecture.md` Section 10 for the full dependency graph including P2/P3 phases.

## Database

SQLite at `data/phantom.db`. WAL mode. All state changes within a single bar are atomic (one transaction per bar). IDs are TEXT (ULIDs). Timestamps are ISO 8601 TEXT. JSON blobs stored as TEXT columns.

Migrations are numbered SQL files in `src/phantom/db/migrations/`. The migration runner applies them in order and tracks applied migrations in a `_migrations` table.
