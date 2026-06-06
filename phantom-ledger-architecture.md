# Phantom Ledger - Software Architecture Design

Project codename: **Phantom Ledger** (working title -- rename at will)

A local-first Python paper trading and backtesting engine with realistic broker cost simulation, multi-account support, and historical position replay.

Usable as both a **Python library** (`from phantom import Phantom`) and a **CLI tool** (`phantom order place ...`). The CLI is a thin wrapper around the library API. All functionality is accessible programmatically.


## 1. Project Structure

```
phantom-ledger/
    pyproject.toml                       # uv project config
    uv.lock                             # lockfile (auto-generated)
    README.md
    .env.example                        # API keys template (Yahoo, Alpaca, etc.)

    src/
        phantom/
            __init__.py                 # Public API re-exports (Phantom, Account, etc.)
            cli.py                      # Typer CLI (thin wrapper around api/)

            # --- Public API ---
            api/
                __init__.py
                client.py              # Phantom: top-level facade (the main entry point)
                accounts.py            # AccountAPI: create, list, show, delete
                orders.py              # OrderAPI: place, cancel, list
                positions.py           # PositionAPI: list, show, close, modify
                notes.py               # NoteAPI: add, list, show, edit
                data_api.py            # DataAPI: fetch prices, rates
                brokers.py             # BrokerAPI: list, show, validate
                reports.py             # ReportAPI: metrics, cost comparison
                runner.py              # RunnerAPI: backtest, paper trade, replay

            # --- Domain Models ---
            models/
                __init__.py
                account.py              # Account, AccountType enum
                broker.py              # BrokerProfile and all sub-models
                order.py               # Order, OrderType, OrderStatus enums
                position.py            # Position, ClosedTrade
                note.py                # TradeNote metadata
                equity.py              # EquityPoint, EquityCurve
                events.py              # Domain events (fill, margin_call, etc.)

            # --- Core Engine ---
            engine/
                __init__.py
                simulation.py          # Unified backtest + paper trade loop
                order_manager.py       # Order lifecycle state machine
                position_manager.py    # Position open/close/update logic
                margin_engine.py       # Margin level checks, stop-out cascade
                replay.py             # Historical position insertion + replay
                clock.py              # Time abstraction (historical vs wall-clock)

            # --- Cost Models ---
            costs/
                __init__.py
                commission.py          # CommissionModel implementations
                spread.py             # SpreadModel implementations
                slippage.py           # SlippageModel implementations
                overnight.py          # OvernightModel + reference rate lookup
                fx.py                 # FX conversion cost
                dividend.py           # DividendModel + withholding calc

            # --- Data Layer ---
            data/
                __init__.py
                price_store.py         # Local price cache (Parquet read/write)
                yahoo.py              # price_cache submodule ( git@github.com:best-testing-monkey/price_cache.git ) wrapper
                alpaca.py             # Alpaca API client (paper trading data)
                rates.py              # SOFR/ESTR/SONIA fetcher (central bank APIs)
                dividends.py          # Dividend calendar fetcher
                provider.py           # DataProvider protocol (abstracts source)

            # --- Persistence ---
            db/
                __init__.py
                database.py           # SQLite connection, migrations
                migrations/           # Versioned SQL migration files
                    001_initial.sql
                    002_add_algorithm_fields.sql
                    ...
                repositories/
                    __init__.py
                    account_repo.py
                    order_repo.py
                    position_repo.py
                    note_repo.py
                    equity_repo.py
                    broker_repo.py

            # --- Notes ---
            notes/
                __init__.py
                manager.py            # File-based note CRUD
                indexer.py            # Note search/listing

            # --- Reporting ---
            reports/
                __init__.py
                metrics.py            # Sharpe, Sortino, drawdown, win rate, etc.
                equity_curve.py       # Equity curve computation + aggregation
                cost_comparison.py    # Cross-broker cost analysis
                formatters.py         # CLI table/chart output formatting

            # --- Broker Profiles ---
            profiles/
                __init__.py
                loader.py             # Load/validate JSON profile configs
                degiro.json
                ibkr.json
                xtb.json

            # --- Alerts (Phase 3) ---
            alerts/
                __init__.py
                dispatcher.py
                telegram.py
                discord.py

            # --- Config ---
            config.py                 # App-wide settings, paths, env loading

    data/                             # Runtime data directory
        prices/                       # Parquet price cache
        rates/                        # Cached reference rates
        notes/                        # Trade note markdown files
            {account_id}/
                {position_id}/
                    001_thesis.md
                    002_update.md
        phantom.db                    # SQLite database

    tests/
        conftest.py
        fixtures/                     # Sample broker profiles, price data
        unit/
            test_commission.py
            test_spread.py
            test_slippage.py
            test_overnight.py
            test_margin.py
            test_order_manager.py
            test_position_manager.py
            test_replay.py
            test_dividend.py
        integration/
            test_backtest_loop.py
            test_paper_trade_loop.py
            test_historical_insertion.py
            test_cost_comparison.py
```


## 2. pyproject.toml

```toml
[project]
name = "phantom-ledger"
version = "0.1.0"
description = "Local paper trading and backtesting engine with realistic cost simulation"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "yfinance>=0.2",
    "httpx>=0.27",
    "pandas>=2.2",
    "pyarrow>=17",
    "rich>=13",
    "pydantic>=2.8",
    "apscheduler>=3.10",
    "python-ulid>=2",
]

[project.scripts]
phantom = "phantom.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
dev-dependencies = [
    "pytest>=8",
    "pytest-cov>=5",
    "ruff>=0.5",
]
```


## 3. Database Schema

All tables use TEXT for IDs (ULIDs or UUIDs generated in Python).
Timestamps stored as ISO 8601 TEXT for SQLite portability.

```sql
-- 001_initial.sql

CREATE TABLE broker_profiles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    config_json     TEXT NOT NULL,           -- full BrokerProfile serialized
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE accounts (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    account_type    TEXT NOT NULL CHECK(account_type IN
                        ('pattern', 'manual', 'algorithm', 'aggregate')),
    broker_profile_id TEXT REFERENCES broker_profiles(id),
    base_currency   TEXT NOT NULL DEFAULT 'EUR',
    initial_capital REAL NOT NULL,
    cash            REAL NOT NULL,
    created_at      TEXT NOT NULL,

    -- type-specific (nullable)
    pattern_tag         TEXT,                -- pattern accounts
    algorithm_id        TEXT,                -- algorithm accounts
    algorithm_version   TEXT,
    algorithm_params    TEXT,                -- JSON blob
    child_account_ids   TEXT                 -- JSON array for aggregate accounts
);

CREATE TABLE orders (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    ticker          TEXT NOT NULL,
    instrument_type TEXT NOT NULL CHECK(instrument_type IN ('stock', 'cfd')),
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    order_type      TEXT NOT NULL CHECK(order_type IN
                        ('market', 'limit', 'stop', 'stop_limit',
                         'trailing_stop', 'oco')),
    quantity        REAL NOT NULL,
    limit_price     REAL,
    stop_price      REAL,
    trailing_amount REAL,
    trailing_pct    REAL,

    -- TP/SL for the resulting position (set at order time)
    take_profit     REAL,
    stop_loss       REAL,

    -- lifecycle
    status          TEXT NOT NULL CHECK(status IN
                        ('pending', 'triggered', 'filled', 'expired',
                         'rejected', 'cancelled')),
    created_at      TEXT NOT NULL,           -- can be historical
    triggered_at    TEXT,
    filled_at       TEXT,
    fill_price      REAL,
    good_til        TEXT,                    -- expiry datetime, NULL = GTC
    max_close_datetime TEXT,                 -- hard deadline for resulting position
    rejection_reason TEXT,

    -- link to position if filled
    position_id     TEXT REFERENCES positions(id)
);

CREATE TABLE positions (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    ticker          TEXT NOT NULL,
    instrument_type TEXT NOT NULL CHECK(instrument_type IN ('stock', 'cfd')),
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),

    -- entry
    entry_order_id  TEXT NOT NULL REFERENCES orders(id),
    entry_price     REAL NOT NULL,
    entry_datetime  TEXT NOT NULL,
    quantity        REAL NOT NULL,
    notional        REAL NOT NULL,

    -- exit conditions
    take_profit     REAL,
    stop_loss       REAL,
    trailing_stop_amount REAL,
    trailing_stop_pct    REAL,
    trailing_stop_peak   REAL,               -- tracked high/low for trailing
    max_close_datetime   TEXT,

    -- cost accumulators
    commission_entry REAL NOT NULL DEFAULT 0,
    commission_exit  REAL NOT NULL DEFAULT 0,
    spread_cost     REAL NOT NULL DEFAULT 0,
    slippage_cost   REAL NOT NULL DEFAULT 0,
    overnight_costs REAL NOT NULL DEFAULT 0,
    dividend_adjustments REAL NOT NULL DEFAULT 0,
    fx_conversion_cost   REAL NOT NULL DEFAULT 0,

    -- margin (CFD)
    margin_required REAL NOT NULL DEFAULT 0,
    leverage        REAL NOT NULL DEFAULT 1.0,

    -- exit
    exit_price      REAL,
    exit_datetime   TEXT,
    realized_pnl    REAL,
    status          TEXT NOT NULL CHECK(status IN
                        ('open', 'closed', 'liquidated')),
    close_reason    TEXT CHECK(close_reason IN
                        ('tp', 'sl', 'trailing_sl', 'max_time',
                         'margin_call', 'manual', NULL)),

    -- metadata
    pattern_tag     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE trade_notes (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    title           TEXT NOT NULL,
    file_path       TEXT NOT NULL,            -- relative path under data/notes/
    content_size    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE equity_curve (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    timestamp       TEXT NOT NULL,
    equity          REAL NOT NULL,
    cash            REAL NOT NULL,
    unrealized_pnl  REAL NOT NULL,
    used_margin     REAL NOT NULL DEFAULT 0,
    drawdown_pct    REAL NOT NULL DEFAULT 0
);

CREATE TABLE overnight_log (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    date            TEXT NOT NULL,
    reference_rate  REAL NOT NULL,
    charge          REAL NOT NULL
);

CREATE TABLE dividend_log (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    ex_date         TEXT NOT NULL,
    gross_amount    REAL NOT NULL,
    net_amount      REAL NOT NULL,
    withholding     REAL NOT NULL
);

-- Indexes
CREATE INDEX idx_orders_account ON orders(account_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_positions_account ON positions(account_id);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_equity_account_ts ON equity_curve(account_id, timestamp);
CREATE INDEX idx_notes_position ON trade_notes(position_id);
```


## 4. Key Component Interactions

```
                          +------------------+
                          |     CLI (Typer)   |
                          +--------+---------+
                                   |
                    +--------------+--------------+
                    |                             |
            +-------v--------+          +---------v--------+
            | SimulationEngine|          |  ReportingEngine  |
            +-------+--------+          +---------+--------+
                    |                             |
         +----------+----------+                  |
         |          |          |                  |
    +----v---+ +---v----+ +---v------+    +------v------+
    | Order  | |Position| | Margin   |    |   Metrics   |
    |Manager | |Manager | | Engine   |    |  Calculator |
    +----+---+ +---+----+ +---+------+    +------+------+
         |         |          |                  |
         +----+----+----+-----+                  |
              |         |                        |
        +-----v----+ +--v---------+       +------v------+
        |CostEngine| |DataProvider|       | Repositories|
        +-----+----+ +--+---------+       +------+------+
              |          |                        |
     +--------+--+  +----+------+          +------v------+
     |Commission | |Yahoo/     |          |   SQLite    |
     |Spread     | |Alpaca/    |          +-------------+
     |Slippage   | |CentralBank|
     |Overnight  | +-----------+
     |FX/Dividend|
     +-----------+
```


## 5. Core Abstractions

### 5.1 Clock Protocol

The clock abstraction is what lets the same engine code run in backtest and paper-trade mode without branching.

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def advance(self) -> datetime | None: ...   # next bar, or None if done
    def is_market_open(self) -> bool: ...

class BacktestClock(Clock):
    """Steps through historical bars instantly."""
    def __init__(self, bars: pd.DatetimeIndex): ...

class LiveClock(Clock):
    """Returns wall-clock time. advance() blocks until next scheduled tick."""
    def __init__(self, interval_seconds: int): ...
```

### 5.2 DataProvider Protocol

```python
class DataProvider(Protocol):
    def get_bars(self, ticker: str, start: datetime,
                 end: datetime) -> pd.DataFrame: ...
    def get_current_price(self, ticker: str) -> float: ...
    def get_bid_ask(self, ticker: str) -> tuple[float, float] | None: ...
    def get_dividends(self, ticker: str, start: datetime,
                      end: datetime) -> list[DividendEvent]: ...

class HistoricalProvider(DataProvider):
    """Fetches via price_cache submodule ( git@github.com:best-testing-monkey/price_cache.git )."""
    ...

class LiveProvider(DataProvider):
    """Reads from Yahoo/Alpaca live feed."""
    ...
```

### 5.3 CostEngine

Single entry point that composes all cost sub-models from a BrokerProfile.

```python
class CostEngine:
    def __init__(self, profile: BrokerProfile): ...

    def entry_costs(self, price: float, quantity: float,
                    ticker: str, instrument_type: str,
                    atr: float | None, hour_utc: int,
                    fx_required: bool) -> CostBreakdown: ...

    def exit_costs(self, price: float, quantity: float,
                   ticker: str, instrument_type: str,
                   atr: float | None, hour_utc: int,
                   fx_required: bool) -> CostBreakdown: ...

    def overnight_cost(self, notional: float, direction: str,
                       reference_rate: float) -> float: ...

    def dividend_adjustment(self, gross: float, direction: str,
                            instrument_type: str,
                            country: str) -> float: ...

@dataclass
class CostBreakdown:
    commission: float
    spread: float
    slippage: float
    fx: float
    total: float
```


## 6. Broker Profile Format (JSON)

```json
// profiles/degiro.json
{
    "profile": {
        "name": "DEGIRO",
        "min_order_size": 1.0,
        "max_leverage": 1.0,
        "supported_instruments": ["stock", "etf"],
        "fx_conversion_pct": 0.0025,
        "fx_base_currency": "EUR"
    },

    "commission": {
        "model_type": "fixed",
        "fixed_fee": 1.00
    },

    "spread": {
        "model_type": "dynamic",
        "base_spread_pct": 0.0005,
        "volatility_multiplier": 0.3,
        "time_of_day_curve": {
            "0": 3.0,
            "9": 1.2,
            "14": 0.8,
            "16": 1.0,
            "20": 2.0
        }
    },

    "slippage": {
        "model_type": "fixed_pct",
        "fixed_pct": 0.0003
    },

    "overnight": {
        "long_markup_pct": 0.0,
        "short_markup_pct": 0.0,
        "day_divisor": 365,
        "rate_source": "manual",
        "manual_rate": 0.0
    },

    "margin": {
        "default_margin_pct": 1.0,
        "margin_call_level": 1.0,
        "stop_out_level": 0.5
    },

    "dividend": {
        "cfd_dividend_adjustment": 1.0,
        "cfd_short_dividend_charge": 1.0,
        "withholding_rates": {
            "US": 0.15,
            "NL": 0.15,
            "DE": 0.26375,
            "UK": 0.0,
            "HK": 0.0
        }
    },

    "trading_hours": {
        "timezone": "America/New_York",
        "open": "09:30",
        "close": "16:00",
        "pre_market": false,
        "post_market": false
    }
}
```


## 7. CLI Interface

```
phantom account create --name "insider_buys" --type pattern \
    --broker degiro --capital 10000 --currency EUR --pattern insider_cluster

phantom account create --name "discretionary" --type manual \
    --broker ibkr --capital 25000 --currency EUR

phantom account create --name "all" --type aggregate \
    --children insider_buys,discretionary

phantom account list
phantom account show insider_buys

phantom order place --account insider_buys --ticker AAPL \
    --direction long --type market --quantity 10 \
    --tp 220 --sl 180 --at "2025-06-15T14:30:00"

phantom order place --account insider_buys --ticker ASML.AS \
    --direction long --type limit --quantity 5 --limit-price 850 \
    --instrument cfd --tp 920 --sl 810 \
    --max-close "2025-12-31T23:59:59" \
    --at "2025-09-01T09:00:00"

phantom order list --account insider_buys --status open
phantom order cancel <order-id>

phantom position list --account insider_buys --status open
phantom position show <position-id>
phantom position close <position-id> --reason manual
phantom position modify <position-id> --tp 230 --sl 185

phantom replay --account insider_buys
    # replays all historical positions from entry to now

phantom run --account insider_buys --mode paper --interval 300
    # paper trade loop, tick every 5 minutes

phantom note add <position-id> --title "Entry thesis" --file ./notes/thesis.md
phantom note add <position-id> --title "Exit review"
    # opens $EDITOR for inline composition
phantom note list <position-id>
phantom note show <note-id>

phantom report --account insider_buys
phantom report --account all --type aggregate
phantom report --compare-brokers degiro,ibkr,xtb --account insider_buys

phantom data fetch --ticker AAPL --start 2024-01-01
phantom data fetch-rates --rate SOFR --start 2024-01-01

phantom broker list
phantom broker show degiro
```


## 8. Library API

The library is the primary interface. The CLI delegates to it entirely. External consumers (scripts, notebooks, other tools, the insider signal pipeline) use the same API.

### 8.1 Top-Level Facade

```python
from phantom import Phantom

# Initialize with a data directory (contains DB, price cache, notes)
ph = Phantom(data_dir="./data")

# Or use an in-memory DB for throwaway experiments
ph = Phantom(data_dir="./data", in_memory=True)
```

The `Phantom` instance exposes sub-APIs as attributes. All operations go through these -- no reaching into internal modules.

### 8.2 Sub-APIs and Usage Examples

```python
# --- Broker Profiles ---
ph.brokers.load("./profiles/degiro.json")
ph.brokers.list()
profile = ph.brokers.get("DEGIRO")

# --- Accounts ---
account = ph.accounts.create(
    name="insider_buys",
    account_type="pattern",
    broker="DEGIRO",
    capital=10000,
    currency="EUR",
    pattern_tag="insider_cluster",
)
ph.accounts.list()
ph.accounts.get("insider_buys")
ph.accounts.delete("insider_buys", confirm=True)

# --- Orders ---
order = ph.orders.place(
    account="insider_buys",
    ticker="AAPL",
    direction="long",
    order_type="market",
    quantity=10,
    take_profit=220.0,
    stop_loss=180.0,
    at="2025-06-15T14:30:00",           # historical entry
)
ph.orders.list(account="insider_buys", status="pending")
ph.orders.cancel(order.id)

# --- Positions ---
positions = ph.positions.list(account="insider_buys", status="open")
position = ph.positions.get(position_id)
ph.positions.modify(position_id, take_profit=230.0, stop_loss=185.0)
ph.positions.close(position_id, reason="manual")

# --- Replay ---
results = ph.runner.replay(account="insider_buys")
result = ph.runner.replay_position(position_id)

# --- Backtest ---
ph.runner.backtest(
    account="insider_buys",
    start="2024-01-01",
    end="2025-06-01",
)

# --- Paper Trade ---
ph.runner.paper_trade(
    account="insider_buys",
    interval_seconds=300,
)
# blocks until SIGINT; call ph.runner.stop() from another thread

# --- Data ---
ph.data.fetch_prices("AAPL", start="2024-01-01")
ph.data.fetch_rates("SOFR", start="2024-01-01")

# --- Notes ---
note = ph.notes.add(
    position_id=position_id,
    title="Entry thesis",
    content="# Why I'm entering\n\nThe cluster buy signal..."
)
ph.notes.add_from_file(position_id, title="Analysis", path="./thesis.md")
ph.notes.list(position_id)
ph.notes.get(note.id)

# --- Reporting ---
report = ph.reports.account_metrics("insider_buys")
report.total_return
report.max_drawdown
report.sharpe
report.cost_breakdown

comparison = ph.reports.compare_brokers(
    account="insider_buys",
    brokers=["DEGIRO", "IBKR", "XTB"],
)

# --- Cost Engine (standalone use) ---
from phantom.costs import CostEngine

engine = CostEngine(profile)
costs = engine.entry_costs(
    price=185.0, quantity=10, ticker="AAPL",
    instrument_type="stock", atr=3.2, hour_utc=14,
    fx_required=True,
)
costs.total
costs.commission
costs.spread
```

### 8.3 Design Principles

The API follows these rules:

- **Strings in, objects out.** Methods accept plain strings and floats as arguments (account names, ticker symbols, ISO datetime strings). They return typed Pydantic models. This keeps the calling code simple -- no need to construct model instances just to pass them in.
- **No global state.** Everything hangs off the `Phantom` instance. Multiple instances with different data directories can coexist in the same process (useful for testing or comparing setups).
- **Exceptions over silent failure.** Invalid inputs raise `ValueError`, missing entities raise `NotFoundError`, insufficient funds raise `InsufficientFundsError`, margin violations raise `MarginError`. All are subclasses of `PhantomError`.
- **Return values are complete.** A `place()` call returns the full Order object including computed costs. A `replay_position()` call returns a ReplayResult with the position's final state, full cost breakdown, and the bar-by-bar history of what happened.
- **Thread-safe where it matters.** The paper trade loop runs in a background thread. Reads (list, get, metrics) are safe to call concurrently. Writes (place, close, modify) acquire a lock.
- **CLI is generated from the API.** Every CLI command maps 1:1 to an API method. The CLI module contains no business logic -- it parses arguments, calls the API, and formats output via Rich.

### 8.4 Exception Hierarchy

```python
class PhantomError(Exception): ...
class NotFoundError(PhantomError): ...
class InsufficientFundsError(PhantomError): ...
class MarginError(PhantomError): ...
class ValidationError(PhantomError): ...
class DataError(PhantomError): ...       # price fetch failures, stale cache
class ProfileError(PhantomError): ...    # invalid broker profile JSON
```

### 8.5 CLI as Thin Wrapper

The CLI module imports the API and does nothing else:

```python
# cli.py (sketch)
import typer
from phantom import Phantom

app = typer.Typer()
account_app = typer.Typer()
app.add_typer(account_app, name="account")

def get_phantom() -> Phantom:
    return Phantom(data_dir=os.environ.get("PHANTOM_DATA", "./data"))

@account_app.command("create")
def account_create(
    name: str,
    account_type: str = typer.Option(..., "--type"),
    broker: str = typer.Option(...),
    capital: float = typer.Option(...),
    currency: str = typer.Option("EUR"),
    pattern: str | None = typer.Option(None),
):
    ph = get_phantom()
    account = ph.accounts.create(
        name=name,
        account_type=account_type,
        broker=broker,
        capital=capital,
        currency=currency,
        pattern_tag=pattern,
    )
    rich.print(account)
```


## 9. Epics & Stories

### Terminology

- **Epic**: A large feature area that delivers a coherent capability.
- **Story**: A concrete, implementable unit of work within an epic.
- **Phase**: Stories are tagged with their earliest viable phase (MVP, P2, P3).

---

### EPIC 1: Project Scaffolding

Set up the project structure, tooling, and foundation.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E1-S01 | Initialize uv project with pyproject.toml, src layout, and test directory | MVP |
| E1-S02 | Set up SQLite database module with connection pooling and WAL mode | MVP |
| E1-S03 | Implement migration runner (read and apply numbered .sql files in order, track applied migrations in a `_migrations` table) | MVP |
| E1-S04 | Write initial migration (001_initial.sql) with all MVP tables: accounts, orders, positions, trade_notes, equity_curve | MVP |
| E1-S05 | Create api/ module skeleton: Phantom facade class, sub-API stubs, exception hierarchy | MVP |
| E1-S06 | Create Typer CLI skeleton with subcommand groups (account, order, position, note, report, data, broker, run, replay) -- all commands delegate to api/ | MVP |
| E1-S07 | Implement config module: load .env, resolve data directory paths, validate required settings | MVP |
| E1-S08 | Set up pytest fixtures: in-memory SQLite, Phantom instance with test data dir, sample broker profile, sample price DataFrame | MVP |
| E1-S09 | Configure ruff for linting and formatting rules | MVP |

---

### EPIC 2: Broker Profile System

Define, load, validate, and persist broker cost configurations.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E2-S01 | Define BrokerProfile Pydantic model with all sub-models (CommissionModel, SpreadModel, SlippageModel, OvernightModel, MarginModel, DividendModel, TradingHoursConfig) | MVP |
| E2-S02 | Implement JSON loader: read a .json file, validate against BrokerProfile schema, return typed object | MVP |
| E2-S03 | Write DEGIRO broker profile JSON (stock-only, fixed commission, dynamic spread, NL dividend withholding) | MVP |
| E2-S04 | Implement broker_repo: save/load BrokerProfile JSON to broker_profiles table | MVP |
| E2-S05 | CLI: `phantom broker list` and `phantom broker show <name>` | MVP |
| E2-S06 | Write IBKR broker profile JSON (tiered commission, per-share model, CFD overnight) | P2 |
| E2-S07 | Write XTB broker profile JSON (zero-commission stocks, CFD spread/overnight) | P2 |
| E2-S08 | CLI: `phantom broker validate <file>` -- parse and report errors without saving | P2 |

---

### EPIC 3: Cost Engine

Implement each cost sub-model and compose them into CostEngine.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E3-S01 | Implement CommissionModel.calculate() for "fixed" model type | MVP |
| E3-S02 | Implement SpreadModel.calculate() for "fixed" and "dynamic" model types (base spread + volatility multiplier + time-of-day curve) | MVP |
| E3-S03 | Implement SlippageModel.calculate() for "fixed_pct" model type | MVP |
| E3-S04 | Implement CostEngine: compose sub-models, expose entry_costs() and exit_costs() returning CostBreakdown | MVP |
| E3-S05 | Unit tests: verify commission, spread, slippage calculations against hand-computed expected values across multiple scenarios | MVP |
| E3-S06 | Implement CommissionModel.calculate() for "per_share" and "tiered" model types | P2 |
| E3-S07 | Implement CommissionModel.calculate() for "zero" model type (monthly free volume threshold) | P2 |
| E3-S08 | Implement SlippageModel.calculate() for "volume_based" model type | P2 |
| E3-S09 | Implement SpreadModel with "market" mode (accept live bid/ask override) | P2 |
| E3-S10 | Implement OvernightModel.calculate(): reference rate + broker markup, day divisor, triple swap day | P2 |
| E3-S11 | Implement FX conversion cost: apply fx_conversion_pct when position currency differs from account base_currency | P2 |
| E3-S12 | Implement DividendModel: stock withholding calculation by country code | P2 |
| E3-S13 | Implement DividendModel: CFD dividend adjustment (credit for longs, charge for shorts) | P2 |
| E3-S14 | Unit tests: overnight, FX, dividend cost calculations | P2 |

---

### EPIC 4: Data Layer

Fetch, cache, and serve price and reference rate data.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E4-S01 | Implement HistoricalProvider: fetch OHLCV from price_cache submodule ( git@github.com:best-testing-monkey/price_cache.git ) keyed by ticker | MVP |
| E4-S02 | Implement Parquet cache management: check freshness (last date in cache vs today), append new bars on fetch, handle splits/adjustments by re-downloading | MVP |
| E4-S03 | CLI: `phantom data fetch --ticker AAPL --start 2024-01-01` -- populate local cache | MVP |
| E4-S04 | Implement DataProvider protocol and make HistoricalProvider conform to it | MVP |
| E4-S05 | Implement dividend data fetching: extract ex-dates and amounts from yfinance, cache alongside price data | P2 |
| E4-S06 | Implement reference rate fetcher: SOFR from NY Fed API, ESTR from ECB SDMX API, cache as CSV/Parquet | P2 |
| E4-S07 | CLI: `phantom data fetch-rates --rate SOFR --start 2024-01-01` | P2 |
| E4-S08 | Implement LiveProvider: get_current_price() via yfinance real-time, get_bid_ask() via Alpaca free API | P2 |
| E4-S09 | Implement data staleness detection: warn if cache is older than N days when entering paper-trade mode | P2 |

---

### EPIC 5: Account System

Create and manage accounts of all four types.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E5-S01 | Implement Account model (Pydantic) with account_type enum (pattern, manual, algorithm, aggregate) | MVP |
| E5-S02 | Implement account_repo: create, read, update, list, delete accounts in SQLite | MVP |
| E5-S03 | CLI: `phantom account create` with --type, --broker, --capital, --currency, and type-specific flags (--pattern, --algorithm-id, --algorithm-version, --children) | MVP |
| E5-S04 | CLI: `phantom account list` (tabular display with Rich) and `phantom account show <name>` | MVP |
| E5-S05 | Implement aggregate account computation: iterate child accounts, sum equity curves, compute combined metrics (no own positions) | P2 |
| E5-S06 | Implement account-level margin tracking: used_margin, free_margin, margin_level as computed properties from open CFD positions | P2 |
| E5-S07 | Validation: reject short/CFD orders on accounts whose broker profile does not list "cfd" in supported_instruments | P2 |
| E5-S08 | CLI: `phantom account delete <name>` with confirmation prompt and cascade warning | P2 |

---

### EPIC 6: Order System

Place, track, and execute orders through their lifecycle.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E6-S01 | Implement Order model with all fields: type, direction, prices, status, timestamps, good_til, max_close_datetime | MVP |
| E6-S02 | Implement order_repo: create, read, update status, list by account/status | MVP |
| E6-S03 | Implement OrderManager.place(): validate order against account state (sufficient cash/margin), persist as "pending" | MVP |
| E6-S04 | Implement OrderManager.evaluate(): given a price bar, check if pending orders should trigger/fill. Market orders fill immediately. Limit orders fill when price reaches limit. | MVP |
| E6-S05 | On fill: compute entry costs via CostEngine, deduct from account cash, create Position record, link order to position | MVP |
| E6-S06 | Implement order expiry: on each bar, expire orders past good_til datetime | MVP |
| E6-S07 | CLI: `phantom order place` with all flags (--at for historical timestamp) | MVP |
| E6-S08 | CLI: `phantom order list`, `phantom order cancel <id>` | MVP |
| E6-S09 | Implement Stop order: trigger market order when price crosses stop_price | P2 |
| E6-S10 | Implement Stop-Limit order: trigger limit order when price crosses stop_price | P2 |
| E6-S11 | Implement Trailing Stop order: track peak price, trigger when price retraces by trailing_amount or trailing_pct | P2 |
| E6-S12 | Implement OCO (One-Cancels-Other): link TP and SL orders, cancel sibling on fill | P2 |
| E6-S13 | Implement margin validation on order placement: reject if insufficient free margin for CFD orders | P2 |
| E6-S14 | Implement order rejection reasons: insufficient funds, margin, outside trading hours, unsupported instrument | P2 |

---

### EPIC 7: Position System

Manage position lifecycle from open through exit.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E7-S01 | Implement Position model with all fields: entry, exit conditions, cost accumulators, status, close_reason | MVP |
| E7-S02 | Implement position_repo: create, read, update, list by account/status/ticker | MVP |
| E7-S03 | Implement PositionManager.update(): given a price bar, update unrealized P&L, check TP/SL | MVP |
| E7-S04 | Implement TP/SL exit logic: detect when bar high/low crosses TP or SL, close position at trigger price, compute exit costs, record close_reason | MVP |
| E7-S05 | Implement TP/SL ambiguity handling: when a single bar crosses both, configurable behavior (conservative = SL first, optimistic = TP first, proximity = closest to open) | MVP |
| E7-S06 | Implement max_close_datetime: auto-close position when clock reaches deadline | MVP |
| E7-S07 | Implement manual close: CLI `phantom position close <id> --reason manual`, compute exit costs at current price | MVP |
| E7-S08 | Implement position modify: CLI `phantom position modify <id> --tp X --sl Y` | MVP |
| E7-S09 | CLI: `phantom position list` and `phantom position show <id>` (display costs breakdown, unrealized P&L, holding duration) | MVP |
| E7-S10 | Implement trailing stop tracking: update peak on each bar, trigger when retracement exceeds threshold | P2 |
| E7-S11 | Implement overnight cost accrual: for each trading day boundary crossed, calculate and accumulate overnight charge using OvernightModel + reference rate | P2 |
| E7-S12 | Implement overnight_log: persist each daily charge to overnight_log table for auditability | P2 |
| E7-S13 | Implement dividend processing: on ex-date, apply DividendModel adjustment to position (credit for long stock, CFD adjustment, charge for short CFD) | P2 |
| E7-S14 | Implement dividend_log: persist each dividend event | P2 |
| E7-S15 | Implement margin tracking per position: compute margin_required based on MarginModel + notional, update account used_margin | P2 |
| E7-S16 | Implement stock vs CFD position behavior: stocks have no overnight cost and no leverage; CFDs carry overnight, margin, and leverage. Controlled by instrument_type on the position. | P2 |

---

### EPIC 8: Margin Engine

Margin level monitoring and forced liquidation.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E8-S01 | Implement MarginEngine.check(): compute margin_level = equity / used_margin for an account, return status (ok / margin_call / stop_out) | P2 |
| E8-S02 | Implement margin call warning: log event, flag account, persist warning timestamp | P2 |
| E8-S03 | Implement stop-out cascade: when margin_level <= stop_out_level, force-close the position with the largest unrealized loss. Repeat until margin_level recovers or all positions closed. Set close_reason = "margin_call". | P2 |
| E8-S04 | Integration test: create account with multiple CFD positions, drop price to trigger stop-out, verify correct cascade order and final account state | P2 |
| E8-S05 | Implement margin level display in `phantom account show` and `phantom position list` for CFD accounts | P2 |

---

### EPIC 9: Simulation Engine

The unified backtest and paper-trade execution loop.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E9-S01 | Implement BacktestClock: step through a DatetimeIndex of bar timestamps, expose now() and advance() | MVP |
| E9-S02 | Implement SimulationEngine.run_backtest(): iterate bars via clock, on each bar call OrderManager.evaluate() then PositionManager.update() for all open positions, record equity point | MVP |
| E9-S03 | Implement equity curve recording: after each bar, compute account equity (cash + sum of position market values), persist EquityPoint | MVP |
| E9-S04 | Integration test: place a market order with TP/SL in the past, run backtest, verify position opens, hits TP or SL, closes with correct P&L and costs | MVP |
| E9-S05 | Implement LiveClock: return wall-clock time, advance() sleeps until next tick interval | P2 |
| E9-S06 | Implement SimulationEngine.run_paper(): same loop as backtest but uses LiveClock + LiveProvider, persists state after each tick | P2 |
| E9-S07 | CLI: `phantom run --account <name> --mode paper --interval 300` | P2 |
| E9-S08 | Implement graceful shutdown: catch SIGINT/SIGTERM, persist current state, log clean exit | P2 |
| E9-S09 | Implement overnight cost accrual hook in simulation loop: detect day boundary crossings, call CostEngine.overnight_cost() for each open CFD position | P2 |
| E9-S10 | Implement dividend hook in simulation loop: check dividend calendar on each bar, apply adjustments via CostEngine | P2 |
| E9-S11 | Implement margin check hook in simulation loop: after position updates, call MarginEngine.check() for accounts with CFD positions | P2 |

---

### EPIC 10: Historical Position Replay

Insert a position at any past date and replay it forward to present.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E10-S01 | Implement ReplayEngine.replay_position(): given a position with historical entry_datetime, load bars from entry to now (or max_close_datetime), step through each bar applying the full position lifecycle (TP/SL/trailing/margin/overnight/dividend) | MVP |
| E10-S02 | Handle replay outcome: if exit condition was hit historically, close the position at historical price/time. If no exit by present, leave position open with status "open" and accumulated costs. | MVP |
| E10-S03 | CLI: `phantom replay --account <name>` -- replay all positions with historical entry dates that haven't been replayed yet | MVP |
| E10-S04 | CLI: `phantom replay --position <id>` -- replay a single position | MVP |
| E10-S05 | Implement replay idempotency: track whether a position has been replayed, prevent double-replay. Store replay_completed_at on position. | MVP |
| E10-S06 | Implement replay with overnight and dividend hooks (depends on E9-S09, E9-S10) | P2 |
| E10-S07 | Implement replay with margin simulation (depends on E8-S01) | P2 |
| E10-S08 | Performance: for bulk replay of many positions on the same ticker, share the price data load across positions | P2 |

---

### EPIC 11: Trade Notes

Attach large markdown notes to positions, stored on filesystem.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E11-S01 | Implement NoteManager: create note file under data/notes/{account_id}/{position_id}/, write metadata to trade_notes table | MVP |
| E11-S02 | Implement note creation from file: `phantom note add <pos-id> --title "Thesis" --file ./my_thesis.md` -- copy file content to note storage | MVP |
| E11-S03 | Implement note creation via $EDITOR: `phantom note add <pos-id> --title "Review"` -- open $EDITOR with temp file, save on close | MVP |
| E11-S04 | CLI: `phantom note list <position-id>` -- list notes with titles, sizes, timestamps | MVP |
| E11-S05 | CLI: `phantom note show <note-id>` -- print note content to stdout (pipe-friendly) | MVP |
| E11-S06 | Implement note size tracking: update content_size on write, warn if approaching 5 MB | MVP |
| E11-S07 | Implement note edit: `phantom note edit <note-id>` -- open existing note in $EDITOR | P2 |
| E11-S08 | Implement note search: grep across all notes in an account for a keyword | P2 |

---

### EPIC 12: Reporting & Analytics

Compute and display performance metrics, equity curves, and cost breakdowns.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E12-S01 | Implement metrics calculator: total return, CAGR, max drawdown, max drawdown duration from equity curve | MVP |
| E12-S02 | Implement trade-level metrics: win rate, average win, average loss, profit factor, expectancy from closed positions | MVP |
| E12-S03 | Implement cost breakdown aggregation: sum commissions, spread, slippage, overnight, FX, dividends across all closed positions in an account | MVP |
| E12-S04 | CLI: `phantom report --account <name>` -- display metrics table and cost breakdown via Rich | MVP |
| E12-S05 | Implement Sharpe ratio and Sortino ratio from daily equity returns | P2 |
| E12-S06 | Implement per-pattern-tag filtering: report metrics for a subset of positions matching a pattern | P2 |
| E12-S07 | Implement per-algorithm-version filtering | P2 |
| E12-S08 | Implement aggregate account reporting: combine equity curves from child accounts, compute portfolio-level metrics | P2 |
| E12-S09 | Implement cost comparison: take a set of closed trades, replay their costs through multiple BrokerProfiles, display side-by-side | P2 |
| E12-S10 | CLI: `phantom report --compare-brokers degiro,ibkr,xtb --account <name>` | P2 |
| E12-S11 | Export equity curve to CSV for external charting | P2 |
| E12-S12 | Implement terminal-based equity curve chart (Rich or plotext) | P3 |

---

### EPIC 13: Paper Trade Scheduler

Automated paper trading on a timer.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E13-S01 | Implement APScheduler integration: configure interval trigger, run simulation tick on schedule | P2 |
| E13-S02 | Implement state persistence per tick: after each tick, commit all position/order/equity changes to DB | P2 |
| E13-S03 | Implement market hours awareness: skip ticks outside trading hours (per broker profile TradingHoursConfig) | P2 |
| E13-S04 | CLI: `phantom run --account <name> --mode paper --interval 300` -- start scheduler, run until SIGINT | P2 |
| E13-S05 | Implement systemd service template for long-running paper trade | P3 |

---

### EPIC 14: Alerts & Notifications

Notify on significant events during paper trading.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E14-S01 | Define alert event types: order_filled, tp_hit, sl_hit, margin_warning, margin_call, position_expired | P3 |
| E14-S02 | Implement alert dispatcher: route events to configured channels | P3 |
| E14-S03 | Implement Telegram webhook sender | P3 |
| E14-S04 | Implement Discord webhook sender | P3 |
| E14-S05 | CLI config: `phantom config alerts --telegram-token <tok> --telegram-chat <id>` | P3 |

---

### EPIC 15: Strategy Automation Hooks

Allow algorithm accounts to run custom strategy logic on each bar.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E15-S01 | Define Strategy protocol: on_bar(bar, account, engine) -> list[OrderRequest] | P3 |
| E15-S02 | Implement strategy loader: discover and import strategy classes from a user-specified directory | P3 |
| E15-S03 | Wire strategy execution into simulation loop: after position updates, call strategy.on_bar(), place returned orders | P3 |
| E15-S04 | Implement strategy parameter snapshot: when an algorithm account is created, serialize strategy params to algorithm_params | P3 |
| E15-S05 | CLI: `phantom run --account <name> --mode backtest --strategy my_strategy.py --start 2024-01-01 --end 2025-01-01` | P3 |

---

### EPIC 16: Web UI

Browser-based interface for monitoring and interaction. Another thin consumer of the library API, like the CLI.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E16-S01 | Set up FastAPI application with CORS, static files, and Jinja2 templates | P3 |
| E16-S02 | Implement dashboard page: account overview, open positions, recent trades | P3 |
| E16-S03 | Implement position detail page with equity chart, cost breakdown, and notes viewer | P3 |
| E16-S04 | Implement order placement form | P3 |
| E16-S05 | Implement broker comparison view | P3 |
| E16-S06 | HTMX integration for live updates during paper trading | P3 |


---

### EPIC 17: Library API Surface

The public Python API that both the CLI and external consumers use. The Phantom facade, sub-API classes, exception hierarchy, and re-exports from `__init__.py`.

| ID     | Story                                                          | Phase |
|--------|----------------------------------------------------------------|-------|
| E17-S01 | Implement PhantomError exception hierarchy: PhantomError, NotFoundError, InsufficientFundsError, MarginError, ValidationError, DataError, ProfileError | MVP |
| E17-S02 | Implement Phantom facade class: accept data_dir and in_memory flag, initialize DB connection, expose sub-API attributes | MVP |
| E17-S03 | Implement AccountAPI: create(), list(), get(), delete() -- delegates to account_repo and validates inputs | MVP |
| E17-S04 | Implement BrokerAPI: load(), list(), get(), validate() -- delegates to profile loader and broker_repo | MVP |
| E17-S05 | Implement OrderAPI: place(), list(), cancel() -- delegates to OrderManager, validates account exists, returns full Order with computed costs | MVP |
| E17-S06 | Implement PositionAPI: list(), get(), close(), modify() -- delegates to PositionManager | MVP |
| E17-S07 | Implement NoteAPI: add(), add_from_file(), list(), get() -- delegates to NoteManager | MVP |
| E17-S08 | Implement RunnerAPI: replay(), replay_position(), backtest() -- delegates to SimulationEngine and ReplayEngine | MVP |
| E17-S09 | Implement DataAPI: fetch_prices(), fetch_rates() -- delegates to data providers | MVP |
| E17-S10 | Implement ReportAPI: account_metrics(), cost_breakdown() -- delegates to metrics calculator | MVP |
| E17-S11 | Set up `phantom/__init__.py` with public re-exports: Phantom, Account, Order, Position, BrokerProfile, CostEngine, PhantomError and subclasses | MVP |
| E17-S12 | Refactor CLI module: strip all business logic, make every command a thin wrapper that calls the corresponding API method and formats output with Rich | MVP |
| E17-S13 | Implement RunnerAPI: paper_trade() with background thread and stop() method | P2 |
| E17-S14 | Implement ReportAPI: compare_brokers() -- run trades through multiple profiles | P2 |
| E17-S15 | Implement NoteAPI: edit(), search() | P2 |
| E17-S16 | Implement thread safety: write lock on mutating operations, concurrent reads safe | P2 |
| E17-S17 | Write library usage documentation with examples (README and/or docs/) | P2 |
| E17-S18 | Implement CostEngine as a standalone public export: usable without a full Phantom instance for quick cost calculations | P2 |


## 10. Dependency Graph (Build Order)

The recommended implementation sequence within each phase, based on dependencies:

```
MVP Critical Path:

E1 (Scaffolding: project, DB, config, API + CLI skeletons)
  |
  +--> E2-S01..S04 (Broker Profile models + JSON + repo)
  |       |
  |       +--> E3-S01..S05 (Cost Engine MVP: commission, spread, slippage)
  |
  +--> E5-S01..S04 (Account system)
  |       |
  |       +--> E6-S01..S08 (Order system)
  |               |
  |               +--> E7-S01..S09 (Position system)
  |                       |
  |                       +--> E9-S01..S04 (Backtest engine)
  |                               |
  |                               +--> E10-S01..S05 (Replay)
  |
  +--> E4-S01..S04 (Data layer: price_cache + Parquet)
  |
  +--> E11-S01..S06 (Trade notes)
  |
  +--> E12-S01..S04 (Reporting MVP)
  |
  +===> E17-S01..S12 (Library API surface + CLI wiring)
        Depends on: all of the above.
        Each sub-API (E17-S03..S10) is built as its underlying
        epic is completed. E17-S11 (re-exports) and E17-S12
        (CLI refactor) are final integration steps.


P2 additions (after MVP is stable):

E3-S06..S14 (Full cost engine) ---+
                                  |
E4-S05..S09 (Dividends, rates,   +--> E9-S09..S11 (Overnight/dividend/margin hooks)
             live feed)           |
                                  +--> E10-S06..S08 (Replay with full costs)
E8-S01..S05 (Margin engine) -----+

E6-S09..S14 (Advanced order types)
E7-S10..S16 (Trailing, overnight, dividends, CFD)
E5-S05..S08 (Aggregate accounts, margin tracking)
E12-S05..S11 (Advanced reporting)
E13-S01..S04 (Paper trade scheduler)
E17-S13..S18 (API: paper trade runner, compare brokers,
              thread safety, docs, standalone CostEngine)


P3 (after P2):

E14 (Alerts)
E15 (Strategy automation)
E16 (Web UI)
```


## 11. Non-Functional Requirements

### 11.1 Performance

- Backtest 5 years of daily bars for 50 tickers in under 60 seconds on a modern desktop.
- Replay of a single historical position: sub-second for any timeframe.
- SQLite WAL mode for concurrent read/write during paper trading.

### 11.2 Data Integrity

- All state changes (order fills, position updates, cost accruals) are atomic within a single DB transaction per bar.
- On crash recovery, the system resumes from the last committed state. No partial bar processing.
- Notes filesystem and DB metadata are kept in sync via a consistency check on startup.

### 11.3 Testability

- All cost models are pure functions: given inputs, deterministic output, no side effects.
- Clock and DataProvider are protocol-based: inject mocks for testing.
- Integration tests use a fixture set of known price data with pre-computed expected outcomes.

### 11.4 Extensibility

- New broker profiles are added by creating a .json file. No code changes needed.
- New cost model types require implementing a new branch in the relevant calculate() method and adding the type string to the model_type enum.
- New order types follow the same pattern: add enum value, implement evaluation logic in OrderManager.
- The library API (Phantom facade) is the integration point for external tools. Consumers depend on the public API surface, not on internal modules. Internal refactors do not break external code as long as the API contract holds.
- CLI, Web UI, and any future interfaces are all consumers of the same library API. Adding a new interface means writing a new thin wrapper, not duplicating logic.

---

## Appendix A: Implementation Standards

This section defines the coding conventions, patterns, and contracts that all implementation work must follow. Every story should be implemented against these standards. When delegating stories to less capable models, prepend this appendix as context.


### A.1 ID Generation

Use ULIDs (Universally Unique Lexicographically Sortable Identifiers) for all entity IDs. They sort chronologically, are URL-safe, and encode creation time.

```python
# src/phantom/utils/ids.py
from ulid import ULID

def new_id() -> str:
    """Generate a new ULID as a 26-character string."""
    return str(ULID())
```

Add `python-ulid` to pyproject.toml dependencies. Never use auto-incrementing integers. Never use UUID4 (no sort order). Every entity gets its ID assigned at creation time in Python, not by the database.


### A.2 Datetime Handling

All datetimes are timezone-aware UTC internally. Accept flexible inputs, store and compare in UTC.

```python
# src/phantom/utils/datetime.py
from datetime import datetime, timezone

def parse_datetime(value: str | datetime) -> datetime:
    """Parse an ISO 8601 string or pass through a datetime.

    Always returns a timezone-aware UTC datetime.
    Raises ValueError if the string is not valid ISO 8601.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def now_utc() -> datetime:
    """Current time in UTC."""
    return datetime.now(timezone.utc)

def to_iso(dt: datetime) -> str:
    """Serialize a datetime to ISO 8601 string for storage."""
    return dt.isoformat()
```

Rules:
- Store in SQLite as ISO 8601 TEXT with timezone offset (e.g. `2025-06-15T14:30:00+00:00`).
- API methods accept `str | datetime` for datetime parameters.
- Comparison and arithmetic always in UTC. Never compare naive and aware datetimes.
- Display to users in their local context only at the CLI/UI layer.


### A.3 Pydantic Models

All domain models use Pydantic v2 `BaseModel`. Not dataclasses, not attrs, not plain dicts.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from phantom.utils.ids import new_id

class Position(BaseModel):
    """A trading position (open or closed)."""

    id: str = Field(default_factory=new_id)
    account_id: str
    ticker: str
    instrument_type: str  # "stock" or "cfd"
    direction: str        # "long" or "short"
    entry_price: float
    entry_datetime: datetime
    quantity: float
    status: str = "open"  # "open", "closed", "liquidated"

    # nullable fields use | None with explicit default
    take_profit: float | None = None
    stop_loss: float | None = None
    close_reason: str | None = None
```

Rules:
- Use `Field(default_factory=new_id)` for IDs, not `Field(default=...)`.
- Nullable fields: always `X | None = None`, never `Optional[X]`.
- Use string literals for enums in models (not Python Enum classes). Validate with Pydantic `field_validator` or `Literal` types.
- Model names are singular nouns: `Position`, `Order`, `Account`, not `Positions`.
- Config: `model_config = ConfigDict(frozen=False)` (mutable by default for engine updates). Use `frozen=True` only for value objects that should never change after creation (e.g. `CostBreakdown`).


### A.4 Enums and Constants

Use `Literal` types for constrained string fields in Pydantic models. Use module-level constants for values referenced outside of models.

```python
# src/phantom/models/types.py
from typing import Literal

AccountType = Literal["pattern", "manual", "algorithm", "aggregate"]
InstrumentType = Literal["stock", "cfd"]
Direction = Literal["long", "short"]
OrderType = Literal["market", "limit", "stop", "stop_limit", "trailing_stop", "oco"]
OrderStatus = Literal["pending", "triggered", "filled", "expired", "rejected", "cancelled"]
PositionStatus = Literal["open", "closed", "liquidated"]
CloseReason = Literal["tp", "sl", "trailing_sl", "max_time", "margin_call", "manual"]
```

Put these in `src/phantom/models/types.py` and import them wherever needed.


### A.5 Exception Patterns

All custom exceptions inherit from `PhantomError`. Raise specific subclasses, never bare `PhantomError`.

```python
# src/phantom/errors.py

class PhantomError(Exception):
    """Base exception for all Phantom Ledger errors."""

class NotFoundError(PhantomError):
    """Entity not found. Raised by repos and API methods."""
    def __init__(self, entity_type: str, identifier: str):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} not found: {identifier}")

class InsufficientFundsError(PhantomError):
    """Account has insufficient cash for the requested operation."""
    def __init__(self, account_id: str, required: float, available: float):
        self.account_id = account_id
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient funds in {account_id}: "
            f"need {required:.2f}, have {available:.2f}"
        )

class MarginError(PhantomError):
    """Margin requirement not met."""

class ValidationError(PhantomError):
    """Invalid input data."""

class DataError(PhantomError):
    """Data fetch or cache failure."""

class ProfileError(PhantomError):
    """Invalid broker profile."""
```

Rules:
- Exception constructors accept structured data, not pre-formatted strings. The structured fields (account_id, required, available) are available to callers for programmatic handling.
- Raise `NotFoundError` when a lookup by ID or name returns no result. Never return `None` from a `.get()` method.
- Raise `ValidationError` for bad inputs caught before hitting the database.
- Raise `ProfileError` for malformed or invalid broker JSON files.
- The CLI layer catches `PhantomError` subclasses and renders them as user-friendly messages via Rich. It never catches bare `Exception`.


### A.6 Repository Conventions

Repositories handle all database I/O. One repo per entity type. All repos follow the same method signatures.

```python
# src/phantom/db/repositories/account_repo.py

import sqlite3
from phantom.models.account import Account
from phantom.errors import NotFoundError

class AccountRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, account: Account) -> Account:
        """Insert a new account. Returns the same object.
        Raises sqlite3.IntegrityError on duplicate ID/name."""
        self._conn.execute(
            "INSERT INTO accounts (id, name, account_type, ...) "
            "VALUES (?, ?, ?, ...)",
            (account.id, account.name, account.account_type, ...),
        )
        self._conn.commit()
        return account

    def get(self, account_id: str) -> Account:
        """Fetch by ID. Raises NotFoundError if not found."""
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Account", account_id)
        return self._row_to_model(row)

    def get_by_name(self, name: str) -> Account:
        """Fetch by name. Raises NotFoundError if not found."""
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Account", name)
        return self._row_to_model(row)

    def list(self, **filters) -> list[Account]:
        """List accounts, optionally filtered.
        Returns empty list if none match."""
        ...

    def update(self, account: Account) -> Account:
        """Update an existing account.
        Raises NotFoundError if ID doesn't exist."""
        cursor = self._conn.execute(
            "UPDATE accounts SET name=?, cash=?, ... WHERE id=?",
            (account.name, account.cash, ..., account.id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Account", account.id)
        self._conn.commit()
        return account

    def delete(self, account_id: str) -> None:
        """Delete by ID. Raises NotFoundError if not found."""
        cursor = self._conn.execute(
            "DELETE FROM accounts WHERE id = ?", (account_id,)
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Account", account_id)
        self._conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Account:
        """Convert a database row to a Pydantic model."""
        return Account(**dict(row))
```

Rules:
- `get()` and `get_by_name()` always raise `NotFoundError` on miss. Never return `None`.
- `list()` returns an empty list on no matches. Never raises on empty results.
- `create()` returns the model passed in (now persisted). Keeps calling code simple.
- `update()` raises `NotFoundError` if the ID doesn't exist (checked via `rowcount`).
- `delete()` raises `NotFoundError` if the ID doesn't exist.
- All write methods call `self._conn.commit()`. For multi-step transactions, the caller passes a connection and manages the transaction boundary explicitly.
- Use `sqlite3.Row` row factory for dict-like access. Set this on connection creation.
- Every repo receives its `sqlite3.Connection` via constructor injection. Never create connections inside repos.


### A.7 API Method Conventions

API classes (in `src/phantom/api/`) are the public surface. They accept simple types, orchestrate repos/engines, and return Pydantic models.

```python
# src/phantom/api/accounts.py

class AccountAPI:
    def __init__(self, conn: sqlite3.Connection, broker_repo: BrokerRepo):
        self._repo = AccountRepo(conn)
        self._broker_repo = broker_repo

    def create(
        self,
        name: str,
        account_type: str,
        broker: str,
        capital: float,
        currency: str = "EUR",
        pattern_tag: str | None = None,
        algorithm_id: str | None = None,
        algorithm_version: str | None = None,
        algorithm_params: dict | None = None,
        children: list[str] | None = None,
    ) -> Account:
        """Create a new account.

        Args:
            name: Unique account name.
            account_type: One of "pattern", "manual", "algorithm", "aggregate".
            broker: Name of a loaded broker profile.
            capital: Starting capital in base currency.
            currency: Account base currency (default EUR).
            pattern_tag: Required for pattern accounts.
            algorithm_id: Required for algorithm accounts.
            algorithm_version: Optional version string for algorithm accounts.
            algorithm_params: Optional frozen params dict for algorithm accounts.
            children: List of child account names for aggregate accounts.

        Returns:
            The created Account.

        Raises:
            ValidationError: If required type-specific fields are missing.
            ProfileError: If the broker profile is not loaded.
            sqlite3.IntegrityError: If the name is already taken.
        """
        # Validate broker exists
        profile = self._broker_repo.get_by_name(broker)

        # Validate type-specific fields
        if account_type == "pattern" and not pattern_tag:
            raise ValidationError(
                "pattern_tag is required for pattern accounts"
            )
        if account_type == "algorithm" and not algorithm_id:
            raise ValidationError(
                "algorithm_id is required for algorithm accounts"
            )

        # Resolve child account IDs for aggregate
        child_account_ids = None
        if account_type == "aggregate" and children:
            child_account_ids = [
                self._repo.get_by_name(c).id for c in children
            ]

        account = Account(
            name=name,
            account_type=account_type,
            broker_profile_id=profile.id,
            base_currency=currency,
            initial_capital=capital,
            cash=capital,
            created_at=now_utc(),
            pattern_tag=pattern_tag,
            algorithm_id=algorithm_id,
            algorithm_version=algorithm_version,
            algorithm_params=algorithm_params,
            child_account_ids=child_account_ids,
        )
        return self._repo.create(account)
```

Rules:
- Method parameters are primitives and simple types: `str`, `float`, `int`, `bool`, `dict`, `list[str]`, `datetime | str`. Never require the caller to construct a Pydantic model to pass in.
- Return types are always Pydantic models or lists of models. Never return dicts or tuples.
- Docstrings follow Google style: one-line summary, Args section, Returns section, Raises section.
- Validation happens in the API layer, not in the repo. The repo trusts its inputs.
- API methods are the transaction boundary for multi-step operations. If placing an order requires checking account balance, computing costs, creating the order, and updating the account, all of that happens in one API method with one commit.


### A.8 CLI Conventions

Every CLI command follows the same pattern: parse args, get Phantom instance, call API method, format output.

```python
import os
import typer
from rich.console import Console
from rich.table import Table
from phantom import Phantom
from phantom.errors import PhantomError

console = Console()

def get_phantom() -> Phantom:
    data_dir = os.environ.get("PHANTOM_DATA", "./data")
    return Phantom(data_dir=data_dir)

@account_app.command("list")
def account_list():
    """List all accounts."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()

        table = Table(title="Accounts")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Broker")
        table.add_column("Capital")
        table.add_column("Cash")

        for a in accounts:
            table.add_row(a.name, a.account_type, ...)

        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
```

Rules:
- The CLI module imports from `phantom` (the public API) and `phantom.errors`. Never import from internal modules (`phantom.db`, `phantom.engine`, etc.).
- Every command wraps its body in `try/except PhantomError`.
- Output formatting uses Rich tables for lists, Rich panels for single-entity display, and `console.print()` for messages.
- Never use `print()`. Always `console.print()`.
- Exit code 0 on success, 1 on `PhantomError`, let unexpected exceptions propagate naturally.
- Destructive commands (delete, close) prompt for confirmation via `typer.confirm()` unless `--yes` flag is passed.


### A.9 Testing Conventions

Tests use pytest. One test file per module. Tests live in `tests/unit/` or `tests/integration/` mirroring the source structure.

```
tests/
    conftest.py                      # shared fixtures
    unit/
        test_commission.py           # tests phantom.costs.commission
        test_spread.py               # tests phantom.costs.spread
        test_account_repo.py         # tests phantom.db.repositories.account_repo
        test_account_api.py          # tests phantom.api.accounts
        ...
    integration/
        test_backtest_loop.py
        test_historical_insertion.py
        ...
```

#### Fixtures (conftest.py)

```python
import pytest
import sqlite3
from phantom import Phantom
from phantom.db.database import run_migrations
from phantom.models.broker import (
    BrokerProfile, CommissionModel, SpreadModel, SlippageModel,
    OvernightModel, MarginModel, DividendModel, TradingHoursConfig,
)

@pytest.fixture
def db_conn():
    """In-memory SQLite with migrations applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    run_migrations(conn)
    yield conn
    conn.close()

@pytest.fixture
def phantom_instance(tmp_path):
    """Full Phantom instance with temp data directory."""
    return Phantom(data_dir=str(tmp_path), in_memory=True)

@pytest.fixture
def degiro_profile():
    """Sample DEGIRO broker profile for testing."""
    return BrokerProfile(
        name="DEGIRO_TEST",
        commission=CommissionModel(model_type="fixed", fixed_fee=1.0),
        spread=SpreadModel(
            model_type="fixed", fixed_spread_pct=0.0005,
        ),
        slippage=SlippageModel(
            model_type="fixed_pct", fixed_pct=0.0003,
        ),
        overnight=OvernightModel(
            long_markup_pct=0.0, short_markup_pct=0.0,
            day_divisor=365, rate_source="manual", manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=1.0,
            margin_call_level=1.0,
            stop_out_level=0.5,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15, "NL": 0.15},
            cfd_dividend_adjustment=1.0,
            cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0025,
        fx_base_currency="EUR",
        min_order_size=1.0,
        max_leverage=1.0,
        trading_hours=TradingHoursConfig(
            timezone="America/New_York",
            open="09:30", close="16:00",
            pre_market=False, post_market=False,
        ),
        supported_instruments=["stock", "etf"],
    )

@pytest.fixture
def sample_price_data():
    """20 days of synthetic OHLCV for AAPL."""
    import pandas as pd
    import numpy as np

    dates = pd.bdate_range("2025-01-02", periods=20)
    base = 185.0
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(20).cumsum() * 0.5
    closes = base + noise

    return pd.DataFrame({
        "Open": closes - rng.random(20) * 0.5,
        "High": closes + rng.random(20) * 1.0,
        "Low": closes - rng.random(20) * 1.0,
        "Close": closes,
        "Adj Close": closes,
        "Volume": rng.integers(1_000_000, 10_000_000, 20),
    }, index=dates)
```

#### Test Structure

```python
# tests/unit/test_commission.py

import pytest
from phantom.costs.commission import CommissionModel

class TestFixedCommission:
    def test_flat_fee_applied(self):
        model = CommissionModel(model_type="fixed", fixed_fee=1.0)
        result = model.calculate(
            quantity=10, price=185.0, monthly_volume=0,
        )
        assert result == 1.0

    def test_flat_fee_independent_of_quantity(self):
        model = CommissionModel(model_type="fixed", fixed_fee=2.50)
        small = model.calculate(
            quantity=1, price=100.0, monthly_volume=0,
        )
        large = model.calculate(
            quantity=1000, price=100.0, monthly_volume=0,
        )
        assert small == large == 2.50

class TestPerShareCommission:
    def test_per_share_basic(self):
        model = CommissionModel(
            model_type="per_share", per_share=0.005,
            per_share_min=1.0, per_share_max_pct=0.01,
        )
        # 500 * 0.005 = 2.50
        result = model.calculate(
            quantity=500, price=50.0, monthly_volume=0,
        )
        assert result == 2.50

    def test_per_share_minimum_applied(self):
        model = CommissionModel(
            model_type="per_share", per_share=0.005,
            per_share_min=1.0, per_share_max_pct=0.01,
        )
        # 10 * 0.005 = 0.05, but min is 1.0
        result = model.calculate(
            quantity=10, price=50.0, monthly_volume=0,
        )
        assert result == 1.0
```

Rules:
- Test class names: `TestXxx` grouped by behavior. Method names: `test_<behavior_being_tested>`.
- Use exact equality (`assert result == 1.0`) for deterministic calculations. Use `pytest.approx()` for floating point only when accumulation error is expected.
- Every cost model test includes at least: one basic case, one edge case (zero, minimum, maximum), and one boundary case.
- Integration tests create a full `Phantom` instance via the fixture and exercise the public API. Never import from internal modules in integration tests.
- Never mock the database. Use the in-memory SQLite fixture. Mock only external HTTP calls (yfinance, price_cache, central bank APIs) using `unittest.mock.patch`.
- Test files must be runnable independently: `pytest tests/unit/test_commission.py`.


### A.10 Import Conventions

```python
# Standard library
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Third party
import pandas as pd
from pydantic import BaseModel, Field

# Internal -- always absolute imports from package root
from phantom.models.account import Account
from phantom.models.types import AccountType, Direction
from phantom.errors import NotFoundError, ValidationError
from phantom.utils.ids import new_id
from phantom.utils.datetime import parse_datetime, now_utc, to_iso
```

Rules:
- Always absolute imports. Never `from .models import ...` relative imports.
- Group: stdlib, blank line, third-party, blank line, internal.
- Import specific names, not modules: `from phantom.errors import NotFoundError`, not `import phantom.errors`.
- Exception: when you need many names from one module, import the module: `from phantom.models import types` then use `types.AccountType`.


### A.11 Logging

Use Python stdlib logging. One logger per module.

```python
import logging

logger = logging.getLogger(__name__)

# In methods:
logger.info("Order %s filled at %.2f", order.id, fill_price)
logger.warning(
    "Margin level %.1f%% below call threshold", margin_level * 100,
)
logger.error("Failed to fetch price data for %s: %s", ticker, exc)
```

Rules:
- Use `%s` formatting in log calls (not f-strings) for lazy evaluation.
- Log levels: `DEBUG` for engine loop details (every bar), `INFO` for significant events (fills, closes, margin calls), `WARNING` for degraded state (stale cache, margin warning), `ERROR` for failures that don't crash (data fetch failure, network timeout).
- Never log at `CRITICAL`. Let exceptions propagate.
- The CLI layer configures the root logger based on a `--verbose` flag. Default is `WARNING`, `--verbose` is `INFO`, `--verbose --verbose` is `DEBUG`.


### A.12 SQL Conventions

- All SQL in repos uses parameterized queries (`?` placeholders). Never f-string or `.format()` SQL.
- Table names are `snake_case` plural: `accounts`, `orders`, `positions`, `trade_notes`.
- Column names are `snake_case` matching the Pydantic model field names exactly.
- JSON blobs stored as TEXT. Serialize with `json.dumps()`, deserialize with `json.loads()` in `_row_to_model()`.
- Foreign keys are enforced: execute `PRAGMA foreign_keys = ON` on every connection.


### A.13 Reference Implementation

Below is a complete vertical slice for the broker profile loader. This is the pattern every other module should follow: model, repo, API method, CLI command, tests.

```python
# =============================================================
# src/phantom/profiles/loader.py
# =============================================================

import json
from pathlib import Path
from phantom.models.broker import BrokerProfile
from phantom.errors import ProfileError

def load_profile(path: str | Path) -> BrokerProfile:
    """Load and validate a broker profile from a JSON file.

    Args:
        path: Path to the .json profile file.

    Returns:
        A validated BrokerProfile instance.

    Raises:
        ProfileError: If the file is missing, unreadable,
                      or fails validation.
    """
    path = Path(path)
    if not path.exists():
        raise ProfileError(f"Profile file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProfileError(f"Invalid JSON in {path}: {e}") from e

    # Flatten nested structure
    profile_section = raw.get("profile", {})
    flat = {
        **profile_section,
        "commission": raw.get("commission", {}),
        "spread": raw.get("spread", {}),
        "slippage": raw.get("slippage", {}),
        "overnight": raw.get("overnight", {}),
        "margin": raw.get("margin", {}),
        "dividend": raw.get("dividend", {}),
        "trading_hours": raw.get("trading_hours", {}),
    }

    try:
        return BrokerProfile(**flat)
    except Exception as e:
        raise ProfileError(
            f"Validation failed for {path}: {e}"
        ) from e


# =============================================================
# src/phantom/db/repositories/broker_repo.py
# =============================================================

import sqlite3
from phantom.models.broker import BrokerProfile
from phantom.errors import NotFoundError
from phantom.utils.ids import new_id
from phantom.utils.datetime import now_utc, to_iso

class BrokerRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, profile: BrokerProfile) -> BrokerProfile:
        """Persist a broker profile."""
        self._conn.execute(
            "INSERT INTO broker_profiles "
            "(id, name, config_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (new_id(), profile.name, profile.model_dump_json(),
             to_iso(now_utc()), to_iso(now_utc())),
        )
        self._conn.commit()
        return profile

    def get_by_name(self, name: str) -> BrokerProfile:
        """Fetch a profile by name."""
        row = self._conn.execute(
            "SELECT config_json FROM broker_profiles WHERE name = ?",
            (name,),
        ).fetchone()
        if row is None:
            raise NotFoundError("BrokerProfile", name)
        return BrokerProfile.model_validate_json(row["config_json"])

    def list(self) -> list[BrokerProfile]:
        """List all loaded profiles."""
        rows = self._conn.execute(
            "SELECT config_json FROM broker_profiles ORDER BY name"
        ).fetchall()
        return [
            BrokerProfile.model_validate_json(r["config_json"])
            for r in rows
        ]

    def delete(self, name: str) -> None:
        """Delete a profile by name."""
        cursor = self._conn.execute(
            "DELETE FROM broker_profiles WHERE name = ?", (name,),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("BrokerProfile", name)
        self._conn.commit()


# =============================================================
# src/phantom/api/brokers.py
# =============================================================

import sqlite3
from phantom.models.broker import BrokerProfile
from phantom.profiles.loader import load_profile
from phantom.db.repositories.broker_repo import BrokerRepo

class BrokerAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._repo = BrokerRepo(conn)

    def load(self, path: str) -> BrokerProfile:
        """Load a broker profile from JSON and persist it.

        Args:
            path: Path to the .json profile file.

        Returns:
            The loaded and persisted BrokerProfile.

        Raises:
            ProfileError: If the file is invalid.
        """
        profile = load_profile(path)
        return self._repo.create(profile)

    def list(self) -> list[BrokerProfile]:
        """List all loaded broker profiles."""
        return self._repo.list()

    def get(self, name: str) -> BrokerProfile:
        """Get a broker profile by name.

        Raises:
            NotFoundError: If no profile with that name is loaded.
        """
        return self._repo.get_by_name(name)

    def validate(self, path: str) -> BrokerProfile:
        """Validate a profile file without persisting.

        Raises:
            ProfileError: If the file is invalid.
        """
        return load_profile(path)


# =============================================================
# CLI: broker commands in cli.py
# =============================================================

@broker_app.command("load")
def broker_load(path: str):
    """Load a broker profile from a JSON file."""
    try:
        ph = get_phantom()
        profile = ph.brokers.load(path)
        console.print(f"Loaded broker profile: {profile.name}")
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)

@broker_app.command("list")
def broker_list():
    """List all loaded broker profiles."""
    try:
        ph = get_phantom()
        profiles = ph.brokers.list()
        table = Table(title="Broker Profiles")
        table.add_column("Name")
        table.add_column("Instruments")
        table.add_column("Commission Type")
        table.add_column("FX Cost")
        for p in profiles:
            table.add_row(
                p.name,
                ", ".join(p.supported_instruments),
                p.commission.model_type,
                f"{p.fx_conversion_pct:.2%}",
            )
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


# =============================================================
# tests/unit/test_broker_loader.py
# =============================================================

import pytest
import json
from phantom.profiles.loader import load_profile
from phantom.errors import ProfileError

VALID_PROFILE_DATA = {
    "profile": {
        "name": "TEST",
        "min_order_size": 1.0,
        "max_leverage": 1.0,
        "supported_instruments": ["stock"],
        "fx_conversion_pct": 0.0025,
        "fx_base_currency": "EUR",
    },
    "commission": {"model_type": "fixed", "fixed_fee": 1.0},
    "spread": {"model_type": "fixed", "fixed_spread_pct": 0.001},
    "slippage": {"model_type": "fixed_pct", "fixed_pct": 0.0003},
    "overnight": {
        "long_markup_pct": 0.0, "short_markup_pct": 0.0,
        "day_divisor": 365, "rate_source": "manual",
        "manual_rate": 0.0,
    },
    "margin": {
        "default_margin_pct": 1.0,
        "margin_call_level": 1.0, "stop_out_level": 0.5,
    },
    "dividend": {
        "withholding_rates": {"US": 0.15},
        "cfd_dividend_adjustment": 1.0,
        "cfd_short_dividend_charge": 1.0,
    },
    "trading_hours": {
        "timezone": "America/New_York",
        "open": "09:30", "close": "16:00",
        "pre_market": False, "post_market": False,
    },
}


class TestLoadProfile:
    def test_valid_profile_loads(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text(json.dumps(VALID_PROFILE_DATA))

        result = load_profile(path)
        assert result.name == "TEST"
        assert result.commission.model_type == "fixed"
        assert result.commission.fixed_fee == 1.0
        assert result.fx_conversion_pct == 0.0025

    def test_missing_file_raises_profile_error(self):
        with pytest.raises(ProfileError, match="not found"):
            load_profile("/nonexistent/path.json")

    def test_invalid_json_raises_profile_error(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{this is not json")
        with pytest.raises(ProfileError, match="Invalid JSON"):
            load_profile(path)

    def test_missing_required_field_raises_profile_error(self, tmp_path):
        path = tmp_path / "incomplete.json"
        path.write_text(json.dumps(
            {"profile": {"name": "INCOMPLETE"}}
        ))
        with pytest.raises(ProfileError, match="Validation failed"):
            load_profile(path)


class TestBrokerRepo:
    def test_create_and_get(self, db_conn, degiro_profile):
        from phantom.db.repositories.broker_repo import BrokerRepo
        repo = BrokerRepo(db_conn)
        repo.create(degiro_profile)
        result = repo.get_by_name("DEGIRO_TEST")
        assert result.name == "DEGIRO_TEST"
        assert result.commission.fixed_fee == 1.0

    def test_get_nonexistent_raises(self, db_conn):
        from phantom.db.repositories.broker_repo import BrokerRepo
        from phantom.errors import NotFoundError
        repo = BrokerRepo(db_conn)
        with pytest.raises(NotFoundError):
            repo.get_by_name("NOPE")

    def test_list_empty(self, db_conn):
        from phantom.db.repositories.broker_repo import BrokerRepo
        repo = BrokerRepo(db_conn)
        assert repo.list() == []


class TestBrokerAPI:
    def test_load_persists_profile(self, phantom_instance, tmp_path):
        path = tmp_path / "test.json"
        path.write_text(json.dumps(VALID_PROFILE_DATA))

        phantom_instance.brokers.load(str(path))
        profiles = phantom_instance.brokers.list()
        assert len(profiles) == 1
        assert profiles[0].name == "TEST"

    def test_validate_does_not_persist(self, phantom_instance, tmp_path):
        path = tmp_path / "test.json"
        path.write_text(json.dumps(VALID_PROFILE_DATA))

        result = phantom_instance.brokers.validate(str(path))
        assert result.name == "TEST"
        assert phantom_instance.brokers.list() == []
```

This reference implementation demonstrates the full vertical: model (Pydantic, frozen), file loader (JSON parse + validation + specific exceptions), repo (CRUD with `NotFoundError`), API (simple inputs, model outputs, orchestration), CLI (thin wrapper, Rich output, error handling), and tests (unit + integration, fixtures, edge cases). Every other module in the project follows this same layering.
