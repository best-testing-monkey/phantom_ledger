# Library Reference

Phantom Ledger is importable as a plain Python package once cloned from GitHub (see the [README](../README.md) for install instructions). The entire public surface lives in the `phantom` namespace.

```python
from phantom import (
    Phantom,
    Account, Order, Position,
    BrokerProfile, CostEngine, CostBreakdown,
    PhantomError, NotFoundError, InsufficientFundsError,
    MarginError, ValidationError, DataError, ProfileError,
)
```

---

## `Phantom` — top-level facade

```python
ph = Phantom(data_dir="./data")
ph = Phantom(data_dir="./data", in_memory=True)   # ephemeral SQLite, useful for tests
```

`Phantom` is the only object you construct directly. Everything else is accessed through its sub-API attributes.

| Attribute | Type | Description |
|-----------|------|-------------|
| `ph.accounts` | `AccountAPI` | Create, query, and delete accounts |
| `ph.orders` | `OrderAPI` | Place, list, and cancel orders |
| `ph.positions` | `PositionAPI` | Query, close, and modify positions |
| `ph.notes` | `NoteAPI` | CRUD for markdown trade notes |
| `ph.data` | `DataAPI` | Fetch and cache price data and rates |
| `ph.brokers` | `BrokerAPI` | Load and inspect broker profiles |
| `ph.reports` | `ReportAPI` | Build metrics, equity curves, cost comparisons |
| `ph.runner` | `RunnerAPI` | Run backtests and paper trading |
| `ph.replay` | `RunnerAPI` | Alias for `ph.runner` (same object) — used for `replay_position` |

Multiple instances can coexist. `accounts`, `orders`, and `positions` mutations (`create`, `delete`, `place`, `cancel`†, `close`, `modify`) share one internal `threading.RLock`, so it's safe to call those concurrently across threads on a shared `Phantom` instance. `notes` and `runner`/`replay` are **not** lock-protected — don't call them concurrently on the same instance from multiple threads.

† `orders.cancel()` does not currently take the lock — see [Thread safety](#thread-safety).

### Getting started: loading broker profiles

A fresh `data_dir` has **no broker profiles registered** — `Phantom.__init__` does not seed them automatically. Every `accounts.create(broker=...)` call below assumes the named profile has already been loaded once:

```python
from pathlib import Path
import phantom

ph = phantom.Phantom(data_dir="./data")

# Load every bundled profile (DEGIRO, IBKR, XTB) once per data_dir
profiles_dir = Path(phantom.__file__).parent / "profiles"
for f in profiles_dir.glob("*.json"):
    ph.brokers.load(str(f))
```

The CLI's `phantom broker seed` command does exactly this. Calling `accounts.create(broker="IBKR")` before the profile is loaded raises `NotFoundError`.

---

## `ph.accounts` — `AccountAPI`

### `create`

```python
account = ph.accounts.create(
    name: str,
    account_type: AccountType,      # "manual" | "pattern" | "algorithm" | "aggregate"
    broker: str,                    # broker profile name, e.g. "IBKR"
    capital: float,
    currency: str = "EUR",
    pattern_tag: str | None = None,
    algorithm_id: str | None = None,
    algorithm_version: str | None = None,
    algorithm_params: dict | None = None,
    child_account_ids: list[str] | None = None,
) -> Account
```

Note: account names are **not** enforced unique — creating two accounts with the same `name` both succeed silently (there's no code path that raises `ValidationError` for a duplicate name). Use `ph.accounts.get(id_or_name)` by ID if you need to disambiguate.

```python
# Manual trading account
account = ph.accounts.create(
    name="my-trades", account_type="manual", broker="IBKR",
    capital=10_000.0, currency="USD",
)

# Algorithm account
algo_acct = ph.accounts.create(
    name="sma-cross", account_type="algorithm", broker="DEGIRO",
    capital=5_000.0, currency="EUR",
    algorithm_id="sma_cross", algorithm_version="2.0",
    algorithm_params={"fast": 10, "slow": 20},
)

# Aggregate (portfolio view across children)
portfolio = ph.accounts.create(
    name="portfolio", account_type="aggregate", broker="IBKR",
    capital=0.0,
    child_account_ids=[account.id, algo_acct.id],
)
```

### `get`

```python
account = ph.accounts.get(id_or_name: str) -> Account
```

Accepts either a ULID ID or the human-readable name. Raises `NotFoundError` on miss.

### `list`

```python
accounts = ph.accounts.list(account_type: str | None = None) -> list[Account]
```

Returns all accounts; pass `account_type` to filter.

### `delete`

```python
ph.accounts.delete(account_id: str) -> None
```

Deletes the account row. Irreversible. **Does not cascade**: foreign keys are enforced (`PRAGMA foreign_keys = ON`), so deleting an account that still has orders or positions raises a raw `sqlite3.IntegrityError` (not a `PhantomError` subclass) and leaves the account undeleted. Close/cancel everything under the account first.

### `get_margin_summary`

```python
from phantom.models.account import MarginSummary

summary = ph.accounts.get_margin_summary(account_name: str) -> MarginSummary
```

Returns margin metrics for the account. For non-CFD accounts all values are zero.

```python
@dataclass(frozen=True)
class MarginSummary:
    used_margin: float    # sum of margin_required across open CFD positions
    free_margin: float    # equity - used_margin
    equity: float         # current cash balance
    margin_level: float   # equity / used_margin (inf when used_margin == 0)
```

### `get_aggregate_equity`

```python
curve = ph.accounts.get_aggregate_equity(account_name: str) -> pd.Series
```

For aggregate accounts, combines child account equity curves (outer join + forward-fill). For regular accounts, returns the account's own equity series. Raises `ValidationError` if called on an aggregate account with no children.

---

## `ph.orders` — `OrderAPI`

### `place`

```python
pending_order = ph.orders.place(account_id: str, order: Order) -> Order
```

Validates broker support for the instrument type and direction, then creates the order with `status="pending"` — **`place()` never fills an order itself, even a market order.** Fills happen when the engine evaluates pending orders against a price bar: during `ph.runner.backtest()`, during a paper-trading tick, or immediately via `ph.orders.fill_manual()` below. Raises `ValidationError` or `InsufficientFundsError` on failure (a limit/stop CFD order with insufficient margin can additionally raise `MarginError`; market CFD orders can't be margin-checked at `place()` time since there's no price yet — margin is checked and deducted at fill time instead).

```python
from phantom import Order

# Market order
order = ph.orders.place(
    account_id=account.id,
    order=Order(
        account_id=account.id,
        ticker="AAPL",
        instrument_type="stock",
        direction="long",
        order_type="market",
        quantity=10,
        take_profit=185.00,
        stop_loss=170.00,
    ),
)

# Limit order
limit = ph.orders.place(
    account_id=account.id,
    order=Order(
        account_id=account.id,
        ticker="MSFT",
        instrument_type="stock",
        direction="long",
        order_type="limit",
        quantity=5,
        limit_price=380.00,
    ),
)

# Trailing stop (3% distance)
trail = ph.orders.place(
    account_id=account.id,
    order=Order(
        account_id=account.id,
        ticker="TSLA",
        instrument_type="stock",
        direction="long",
        order_type="trailing_stop",
        quantity=3,
        trailing_pct=3.0,
    ),
)
```

### `list`

```python
orders = ph.orders.list(
    account_name: str | None = None,
    status: str | None = None,         # "pending" | "filled" | "cancelled" | ...
) -> list[Order]
```

**`account_name=None` returns `[]`**, not orders across all accounts (unlike `ph.positions.list()`) — always pass `account_name`.

### `cancel`

```python
cancelled = ph.orders.cancel(order_id: str) -> Order
```

Raises `ValidationError` if the order is not in `pending` status.

### `fill_manual`

```python
filled_order, position = ph.orders.fill_manual(
    order_id: str,
    fill_price: float,
    fill_datetime: datetime | None = None,   # defaults to now_utc()
) -> tuple[Order, Position]
```

The only way to fill a pending order (including a market order) outside a running backtest or paper-trading tick — stamps the order with the given price/time and runs it through the same fill logic the engine uses, creating the resulting `Position`. Raises `ValidationError` if the order is not `pending` or `fill_price <= 0`.

```python
order = ph.orders.place(account_id=account.id, order=Order(
    account_id=account.id, ticker="AAPL", instrument_type="stock",
    direction="long", order_type="market", quantity=10,
))
filled, position = ph.orders.fill_manual(order.id, fill_price=182.50)
```

### `modify`

```python
updated = ph.orders.modify(
    order_id: str,
    limit_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> Order
```

Updates price fields on a still-pending order. Raises `ValidationError` if the order is not `pending`, or if no fields were given.

---

## `ph.positions` — `PositionAPI`

### `list`

```python
positions = ph.positions.list(
    account_name: str | None = None,
    status: str | None = None,              # "open" | "closed" | "liquidated"
    replay_completed_at=...,                # Ellipsis = no filter; None = not replayed
    pattern_tag: str | None = None,
    algorithm_version: str | None = None,
) -> list[Position]
```

**When `account_name` is `None`, `status`/`pattern_tag`/`algorithm_version`/`replay_completed_at` are all silently ignored** — the call is hardcoded to open positions across every account (`ph.positions.list(status="closed")` with no `account_name` still returns *open* positions, not closed ones). Pass `account_name` whenever you use any filter other than the default.

```python
# All open positions
open_positions = ph.positions.list(account_name="my-trades", status="open")

# Closed positions for a specific algorithm version
closed = ph.positions.list(
    account_name="algo-v2",
    status="closed",
    algorithm_version="2.0",
)

# Positions not yet replayed
unreplayed = ph.positions.list(account_name="algo-v2", replay_completed_at=None)
```

### `get`

```python
position = ph.positions.get(position_id: str) -> Position
```

Raises `NotFoundError` on miss.

### `close`

```python
closed_position = ph.positions.close(
    position_id: str,
    close_reason: str = "manual",   # "tp"|"sl"|"trailing_stop"|"max_time"|"margin_call"|"manual"
    exit_price: float | None = None,
    quantity: float | None = None,  # None = close in full
    exit_datetime: datetime | None = None,  # defaults to now_utc()
) -> Position
```

Raises `ValidationError` if position is not open, `exit_price` is not supplied, `quantity <= 0`, or `quantity` exceeds the open size.

Passing `quantity` less than the position's full size does a **partial close**: it decrements `position.quantity`, accumulates the realized P&L on the (still-open) position, and returns that resized position rather than a fully closed one — `updated.status` stays `"open"`.

### `modify`

```python
updated = ph.positions.modify(
    position_id: str,
    take_profit: float | None = None,
    stop_loss: float | None = None,
) -> Position
```

At least one of `take_profit` or `stop_loss` must be provided. Raises `ValidationError` if position is not open.

### `reset_replay`

```python
ph.positions.reset_replay(position_id: str) -> None
```

Clears `replay_completed_at` so the position will be picked up on the next `replay all` run.

---

## `ph.runner` — `RunnerAPI`

### `backtest`

```python
result = ph.runner.backtest(
    account_id: str,
    tickers: list[str],
    start: str | datetime,    # "YYYY-MM-DD" or datetime
    end: str | datetime,
    data_provider=None,       # defaults to HistoricalProvider (price_cache)
    fine_data_provider=None,  # optional finer-resolution provider, see below
) -> BacktestResult
```

Runs the simulation clock bar-by-bar over the union of every ticker's trading days in `[start, end]`. Each step: evaluates any **already-pending** orders for the given `tickers` against that bar (market orders fill unconditionally at that bar's `Open`; limit/stop/trailing orders fill only if triggered), checks open positions' TP/SL, applies overnight/dividend costs on day boundaries, and records an equity point. Orders that can't be funded at fill time are marked `status="rejected"` rather than aborting the run — see `.rejected_orders` below.

There is **no strategy-callback parameter** (an `on_bar` callback was previously documented here but does not exist in the code — `backtest()` takes exactly the six parameters above). To place orders programmatically, call `ph.orders.place()` **before** invoking `backtest()`; a pending order fills on the first bar of the run where its ticker has data. Since orders can only be queued up front, there's no way to react to a bar mid-run within a single `backtest()` call.

**`fine_data_provider`**: when a step's bar brackets both a position's take-profit AND stop-loss level (only that specific ambiguous case — otherwise this is never consulted, so it costs nothing when unused), `backtest()` normally has to guess which hit first via a fixed tie-break (`"conservative"` → always resolves to the stop-loss). Pass any object implementing `DataProvider.get_bars(ticker, start, end)` (e.g. an hourly-resolution provider for a daily-resolution run) and it's used to walk that day's finer bars in order to find which level was actually crossed first. Only affects TP/SL resolution during `backtest()`, not `paper_trade()`/margin-call/stop-out handling.

**To open positions on different dates in one simulated run** (there's no callback to do this from inside the loop), place one order and run `backtest()` in date-range chunks, growing the `tickers` list as each new instrument's start date arrives — previously-opened positions keep having their TP/SL checked in later chunks as long as their ticker stays in the `tickers` list:

```python
tickers = []
for ticker, entry_date, chunk_end, order in trades:   # your own trade plan
    tickers.append(ticker)
    ph.orders.place(account_id=account.id, order=order)
    ph.runner.backtest(account_id=account.id, tickers=tickers, start=entry_date, end=chunk_end)
```

`BacktestResult` (`@dataclass`, not the `.equity_metrics`/`.trade_metrics`/`.positions` shape previously shown here) attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `.account` | `Account` | The account's state at the end of the run |
| `.equity_curve` | `list[EquityPoint]` | Per-bar equity snapshots |
| `.filled_orders` | `list[Order]` | Orders filled during this run |
| `.rejected_orders` | `list[Order]` | Orders that couldn't be funded at fill time (`status="rejected"`) — doesn't abort the run, other orders that step still process |
| `.closed_positions` | `list[Position]` | Positions closed (TP/SL/etc.) during this run |

For Sharpe/CAGR/win-rate style metrics, call `ph.reports.account_metrics(account.name)` after the run (see [`ph.reports`](#ph-reports--reportapi)) rather than reading them off `BacktestResult`.

```python
result = ph.runner.backtest(
    account_id=account.id,
    tickers=["AAPL"],
    start="2023-01-01",
    end="2023-12-31",
)
print(f"Closed {len(result.closed_positions)} positions, ending cash {result.account.cash:.2f}")

metrics = ph.reports.account_metrics(account.name)
print(f"Sharpe: {metrics['equity'].sharpe_ratio:.2f}")
print(f"Trades: {metrics['trades'].trade_count}")
```

### `paper_trade` (blocking)

```python
ph.runner.paper_trade(
    account_id: str,
    tickers: list[str],
    interval: float = 300.0,        # seconds between ticks
    stop_event: threading.Event | None = None,
    data_provider=None,             # defaults to LiveProvider (Yahoo / Alpaca)
) -> None
```

Blocks until `stop_event.set()` is called or `SIGINT` / `SIGTERM` is received. Signals are restored on exit.

```python
import threading
from phantom import Phantom

ph = Phantom(data_dir="./data")
account = ph.accounts.get("live-paper")

stop = threading.Event()
ph.runner.paper_trade(
    account_id=account.id,
    tickers=["AAPL", "MSFT"],
    interval=300,
    stop_event=stop,
)
```

### `paper_trade_background`

```python
handle = ph.runner.paper_trade_background(
    account_id: str,
    tickers: list[str],
    interval: float = 300.0,
    data_provider=None,
) -> PaperTradeHandle
```

Starts the paper trading loop in a daemon thread. Returns immediately.

```python
@dataclass
class PaperTradeHandle:
    def stop(self) -> None: ...         # graceful shutdown (idempotent)
    def is_running(self) -> bool: ...   # True until the background thread exits
```

```python
handle = ph.runner.paper_trade_background(
    account_id=account.id,
    tickers=["AAPL"],
    interval=60,
)

# ... your application runs here ...

handle.stop()
```

### `replay_position`

```python
replayed = ph.runner.replay_position(position: Position) -> Position
```

Also reachable as `ph.replay.replay_position(...)` (`ph.replay` is an alias for the same `RunnerAPI` instance). Re-runs a single position against historical price data via `ReplayEngine`, e.g. to re-evaluate TP/SL/costs for a position created outside a backtest. Pairs with `ph.positions.reset_replay()` above and the CLI's `phantom replay` commands.

---

## `ph.notes` — `NoteAPI`

Notes are stored as markdown files under `$PHANTOM_DATA/notes/{account_id}/{position_id}/`.

```python
# Create from a string
note = ph.notes.create(
    position_id=position.id,
    account_id=account.id,
    title="Entry rationale",
    content="# Why I entered\n\nGolden cross confirmed on daily...",
)

# Create from a file on disk
note = ph.notes.create_from_file(
    position_id=position.id,
    account_id=account.id,
    title="Entry rationale",
    source_path="/tmp/notes/entry.md",
)

# Read content
content: str = ph.notes.read(note_id)

# List all notes for a position
notes = ph.notes.list(position_id)

# Get note metadata
note = ph.notes.get(note_id)

# Update content
updated = ph.notes.update(note_id, content="Updated content...")

# Delete a note (removes both the DB row and the markdown file)
ph.notes.delete(note_id)

# Convenience wrapper around create() — content first, title optional (defaults to "")
note = ph.notes.add(position_id=position.id, account_id=account.id, content="Quick note")

# Search across all notes for an account
from phantom.notes.manager import SearchResult

results: list[SearchResult] = ph.notes.search(account_id=account.id, keyword="golden cross")
# This is a literal line-by-line grep across every .md file under notes/{account_id}/,
# not a per-note title/snippet search:
#   SearchResult.file_path    e.g. "notes/<account_id>/<position_id>/<note_id>.md"
#   SearchResult.line_number  1-indexed line where the keyword matched
#   SearchResult.line         the full matching line's text
```

---

## `ph.data` — `DataAPI`

```python
# Fetch and cache OHLCV data (uses price_cache SQLite backend)
df = ph.data.fetch_prices(
    ticker: str,
    start: datetime,         # datetime only — see caveat below
    end: datetime,
) -> pd.DataFrame            # DatetimeIndex (UTC), columns: Open/High/Low/Close/Volume

# Fetch and cache a reference rate
rates = ph.data.fetch_rates(
    rate: str,               # "SOFR" or "ESTR" (case-insensitive)
    start: datetime,
    end: datetime,
) -> pd.Series
```

Both take `datetime` only (not the `"YYYY-MM-DD"` strings accepted elsewhere in this library, e.g. `ph.runner.backtest()`). `fetch_prices` raises `DataError` on a genuine `price_cache`/network failure — but **passing a string for `start`/`end` does not raise `DataError`**: the type error happens inside a broad `except Exception` in the underlying provider that's meant to catch "no data available," so it's swallowed and an empty `DataFrame` is returned silently. Always pass real `datetime` objects. `fetch_rates` raises `DataError` on network failure or an unrecognized `rate` name.

`ph.data.list()` also exists but is an unimplemented stub — it unconditionally returns `[]`.

---

## `ph.brokers` — `BrokerAPI`

```python
# List profiles already loaded into this data_dir's DB (not the bundled JSON files —
# see "Getting started: loading broker profiles" above to load those first)
profiles = ph.brokers.list() -> list[BrokerProfile]

# Get a loaded profile by name
profile = ph.brokers.get("IBKR") -> BrokerProfile

# Load a JSON profile from disk and persist it into the DB
profile = ph.brokers.load("path/to/my-broker.json") -> BrokerProfile

# Build and persist a profile directly from a dict, instead of a file
profile = ph.brokers.create_from_dict({...}) -> BrokerProfile

# Parse and validate a profile JSON WITHOUT persisting it (dry run)
profile = ph.brokers.validate("path/to/my-broker.json") -> BrokerProfile
```

`get()` raises `NotFoundError` when a named profile hasn't been loaded. `load`/`create_from_dict`/`validate` raise `ProfileError` on malformed JSON or a schema that fails validation.

### `BrokerProfile.margin.classes` — per-instrument margin rates

```python
profile = ph.brokers.get("IBKR")
profile.margin.margin_pct_for("EURUSD=X")  # -> 0.03
profile.margin.margin_pct_for("AAPL")      # -> profile.margin.default_margin_pct (no class matches)
```

`margin.classes` is a per-instrument-class margin-rate table: each entry is either an explicit `symbols` list or a `match` regex (checked via `re.fullmatch`), first match in list order wins, falling back to `default_margin_pct` when nothing matches. It's used internally by `handle_fill()`/`place()` to compute CFD margin — not something most callers touch directly, but worth knowing about if margin amounts look unexpectedly flat (i.e. every order landing on the same `default_margin_pct` regardless of instrument).

The bundled `ibkr.json`/`xtb.json`/`degiro.json` profiles' `classes` cover BOTH broker-house-native ticker spellings (`"EURUSD"`, `"XAUUSD"`, bare `"BTC"`) AND Yahoo Finance/yfinance-style tickers (`"EURUSD=X"`, `"GC=F"`, `"BTC-USD"`, `"^GSPC"`) — but nothing else. A caller using a third ticker convention (or a data source whose symbols don't match either) will silently fall through to `default_margin_pct` for every order, with no error or warning raised. If margin amounts look flatter than expected, check `margin_pct_for()` against your own tickers directly rather than assuming coverage. To patch a loaded profile's `classes` for your own ticker convention, mutate `profile.margin.classes` and call `ph.brokers.update("IBKR", profile)` — it updates an already-loaded profile in place (raises `NotFoundError` if the name hasn't been loaded yet; it's not an upsert).

---

## `ph.reports` — `ReportAPI`

`ReportAPI` has exactly two methods — there is no `equity_metrics()`, `trade_metrics()`, `cost_summary()`, `export_csv()`, or `compare_brokers()` on `ph.reports` (previous versions of this doc described a 5-method surface that was never implemented):

```python
# Equity + trade + cost metrics, built from the account's closed positions.
# Built from realized P&L at each position's exit — NOT the bar-by-bar
# equity_curve a backtest records, so it needs no prior backtest() call.
metrics: dict = ph.reports.account_metrics(account_name)
# {
#   "equity": EquityMetrics,   # present only if there are >= 2 closed positions
#   "trades": TradeMetrics,    # present only if there is >= 1 closed position
#   "costs":  CostSummary,     # always present (aggregated across ALL positions, open or closed)
# }
metrics["costs"].total_cost

# Aggregate cost summary across all of the account's positions (same as metrics["costs"])
costs: CostSummary = ph.reports.cost_breakdown(account_name)
```

Both raise `NotFoundError` if `account_name` doesn't match an account. If you need the equity curve itself (for a chart, or to export to CSV), read it off a `BacktestResult.equity_curve` from `ph.runner.backtest()` — there is no report method that fetches it independently, and no CSV-export or cross-broker-comparison method exposed on `ph.reports` at all (equivalent logic exists as free functions — `export_equity_csv()` in `phantom.reports.exporters` and `compare_broker_costs()` in `phantom.reports.cost_comparison` — but neither is wired up on the public `ReportAPI`).

### `EquityMetrics` fields

| Field | Type | Description |
|-------|------|-------------|
| `total_return_pct` | `float` | Total return as a percentage |
| `cagr_pct` | `float` | Compound annual growth rate (%) |
| `max_drawdown_pct` | `float` | Maximum peak-to-trough drawdown (%) |
| `max_drawdown_duration_days` | `int` | Longest drawdown period in calendar days |
| `sharpe_ratio` | `float` | Annualised Sharpe ratio (√252 scaling) |
| `sortino_ratio` | `float` | Annualised Sortino ratio; `float("inf")` when there are no losing days |

### `TradeMetrics` fields

| Field | Type | Description |
|-------|------|-------------|
| `trade_count` | `int` | Total closed trades |
| `win_count` | `int` | Trades with positive P&L |
| `loss_count` | `int` | Trades with negative P&L |
| `win_rate_pct` | `float` | Win count / trade count × 100 |
| `avg_win` | `float` | Average profit on winning trades |
| `avg_loss` | `float` | Average loss on losing trades (positive number) |
| `gross_profit` | `float` | Sum of all winning trade P&L |
| `gross_loss` | `float` | Sum of all losing trade P&L (positive number) |
| `profit_factor` | `float` | gross_profit / gross_loss |
| `expectancy` | `float` | win_rate × avg_win − loss_rate × avg_loss |

### `CostSummary` fields

| Field | Type | Description |
|-------|------|-------------|
| `total_commission` | `float` | Entry + exit commissions |
| `total_spread` | `float` | Spread cost |
| `total_slippage` | `float` | Slippage cost |
| `total_overnight` | `float` | Overnight / swap charges |
| `total_fx` | `float` | FX conversion cost |
| `total_dividends` | `float` | Dividend adjustments (negative = received) |
| `total_cost` | `float` | Sum of all cost components |

---

## `CostEngine` — standalone cost calculator

`CostEngine` can be used independently of the rest of the library if you only need cost simulation.

```python
from phantom import Phantom, CostEngine

ph = Phantom(data_dir="./data")
profile = ph.brokers.get("IBKR")
engine = CostEngine(profile)

# Entry costs
entry = engine.entry_costs(
    price=180.0,
    quantity=100,
    ticker="AAPL",
    instrument_type="stock",
    atr=2.5,            # Average True Range — used for slippage model
    hour_utc=14,        # Hour of day (UTC) — used for spread model
    fx_required=True,   # Whether a currency conversion is needed
)
print(entry.commission)     # float
print(entry.spread)
print(entry.slippage)
print(entry.fx)

# Exit costs
exit_ = engine.exit_costs(price=190.0, quantity=100, ticker="AAPL",
                           instrument_type="stock", atr=2.5, hour_utc=15,
                           fx_required=True)

# Overnight charge (single night)
charge = engine.overnight_cost(
    notional=18_000.0,
    direction="long",
    reference_rate=0.053,   # e.g. SOFR
)

# Dividend adjustment
net = engine.dividend_adjustment(
    gross=1.50,             # dividend per share × quantity
    direction="long",
    instrument_type="stock",
    country="US",           # ISO country code for withholding tax lookup
)
```

### `CostBreakdown` fields

```python
@dataclass(frozen=True)
class CostBreakdown:
    commission: float
    spread: float
    slippage: float
    fx: float
    total: float
```

Note: `overnight_cost()` and `dividend_adjustment()` above return a plain `float` each, not a `CostBreakdown` — there's no `overnight`/`dividend` field on `CostBreakdown` itself.

---

## Domain models

All models are Pydantic v2 `BaseModel`. IDs are ULIDs (TEXT). Datetimes are timezone-aware UTC.

### `Account`

```python
class Account(BaseModel):
    id: str
    name: str
    account_type: AccountType          # "manual"|"pattern"|"algorithm"|"aggregate"
    broker_profile_id: str
    base_currency: str                 # ISO 4217
    initial_capital: float
    cash: float                        # current cash balance
    created_at: datetime
    pattern_tag: str | None
    algorithm_id: str | None
    algorithm_version: str | None
    algorithm_params: dict | None
    child_account_ids: list[str] | None
    margin_call_at: datetime | None    # set when account is in margin call
```

### `Order`

```python
class Order(BaseModel):
    id: str
    account_id: str
    ticker: str
    instrument_type: InstrumentType    # "stock" | "cfd"
    direction: Direction               # "long" | "short"
    order_type: OrderType              # "market"|"limit"|"stop"|"stop_limit"|"trailing_stop"|"oco"
    quantity: float
    status: OrderStatus                # "pending"|"triggered"|"filled"|"expired"|"rejected"|"cancelled"
    limit_price: float | None
    stop_price: float | None
    trailing_amount: float | None      # absolute trailing distance
    trailing_pct: float | None         # percentage trailing distance
    trailing_peak: float | None        # current peak price tracked by the engine
    take_profit: float | None
    stop_loss: float | None
    created_at: datetime
    triggered_at: datetime | None
    filled_at: datetime | None
    fill_price: float | None
    good_til: datetime | None          # order expiry
    max_close_datetime: datetime | None  # copied onto the resulting Position on fill
    rejection_reason: str | None
    position_id: str | None            # set after fill
    oco_sibling_id: str | None         # linked OCO order
```

### `Position`

```python
class Position(BaseModel):
    id: str
    account_id: str
    ticker: str
    instrument_type: InstrumentType
    direction: Direction
    entry_order_id: str
    entry_price: float
    entry_datetime: datetime
    quantity: float
    notional: float

    # Exit conditions (set at order placement, updated by modify)
    take_profit: float | None
    stop_loss: float | None
    trailing_stop_amount: float | None
    trailing_stop_pct: float | None
    trailing_stop_peak: float | None
    trailing_stop_distance: float | None
    peak_price: float | None
    max_close_datetime: datetime | None

    # Cost accumulators (updated each bar by the engine)
    commission_entry: float
    commission_exit: float
    spread_cost: float
    slippage_cost: float
    overnight_costs: float
    overnight_accrued: float
    last_bar_date: str | None
    dividend_adjustments: float
    fx_conversion_cost: float
    country_code: str | None

    # Margin
    margin_required: float
    leverage: float

    # Exit fields (set on close)
    exit_price: float | None
    exit_datetime: datetime | None
    realized_pnl: float | None
    status: PositionStatus             # "open" | "closed" | "liquidated"
    close_reason: CloseReason | None   # "tp"|"sl"|"trailing_stop"|"max_time"|"margin_call"|"manual"

    # Metadata
    pattern_tag: str | None
    algorithm_version: str | None
    replay_completed_at: str | None
    created_at: datetime

    # Computed
    unrealized_pnl: float              # @computed_field
```

`unrealized_pnl` is currently a **non-functional placeholder**: it always returns `0.0`, for open positions too, not just closed ones — the code comment marks it as needing a current-price input it doesn't yet have. Don't rely on it for open P&L; compute it yourself from a current price and `entry_price`/`quantity`/`direction` if you need it.

---

## Error handling

All errors are subclasses of `PhantomError`. Catch the narrowest subclass you care about.

```python
from phantom import (
    Phantom, Order,
    NotFoundError, InsufficientFundsError, MarginError,
    ValidationError, DataError, ProfileError,
)

ph = Phantom(data_dir="./data")

try:
    account = ph.accounts.get("missing-account")
except NotFoundError as e:
    print(e.entity)      # "Account"
    print(e.identifier)  # "missing-account"

try:
    ph.orders.place(account_id=account.id, order=order)
except InsufficientFundsError as e:
    print(f"Need {e.required:.2f}, have {e.available:.2f}")
except MarginError as e:
    print(f"Margin level: {e.margin_level:.1%}")
except ValidationError as e:
    print(str(e))
```

### Error types

| Exception | Raised when |
|-----------|-------------|
| `NotFoundError` | `get()` finds no matching record. Attributes: `.entity`, `.identifier` |
| `InsufficientFundsError` | Order placement requires more cash than available. Attributes: `.account_id`, `.required`, `.available` |
| `MarginError` | Margin level breached. Attributes: `.account_id`, `.margin_level` |
| `ValidationError` | Invalid input, conflicting parameters, or illegal state transition |
| `DataError` | Price or rate fetch failed (network error, bad ticker) |
| `ProfileError` | Broker profile JSON is malformed or missing required fields |

---

## Type aliases

All string-literal types live in `phantom.models.types`.

```python
AccountType    = Literal["pattern", "manual", "algorithm", "aggregate"]
InstrumentType = Literal["stock", "cfd"]
Direction      = Literal["long", "short"]
OrderType      = Literal["market", "limit", "stop", "stop_limit", "trailing_stop", "oco"]
OrderStatus    = Literal["pending", "triggered", "filled", "expired", "rejected", "cancelled"]
PositionStatus = Literal["open", "closed", "liquidated"]
CloseReason    = Literal["tp", "sl", "trailing_stop", "max_time", "margin_call", "manual"]
```

---

## Testing

`in_memory=True` skips creating the `phantom.db` SQLite file — but `data_dir`'s `prices/`, `rates/`, and `notes/` subdirectories are still created on disk (`ph.notes` always writes real markdown files there, regardless of the in-memory DB), so pass a throwaway `data_dir` in tests, e.g. `tmp_path`.

```python
import pytest
from phantom import Phantom
from phantom.models.order import Order

@pytest.fixture
def ph(tmp_path):
    instance = Phantom(data_dir=str(tmp_path), in_memory=True)
    instance.brokers.load("src/phantom/profiles/degiro.json")   # see "Getting started" above
    return instance

def test_place_and_fill_order(ph):
    account = ph.accounts.create(
        name="test", account_type="manual", broker="DEGIRO", capital=1_000.0
    )
    order = ph.orders.place(
        account_id=account.id,
        order=Order(
            account_id=account.id,
            ticker="AAPL",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=5,
        ),
    )
    assert order.status == "pending"          # place() never fills, even market orders

    filled, position = ph.orders.fill_manual(order.id, fill_price=180.0)
    assert filled.status == "filled"
    assert position.quantity == 5
```

Never mock the database — use the in-memory fixture instead. Mock only external HTTP calls (price fetches, rate fetches) with `unittest.mock.patch`.

---

## Thread safety

`accounts.create`, `accounts.delete`, `orders.place`, `positions.close`, and `positions.modify` are protected by one internal `threading.RLock` shared by those three sub-APIs. Read operations (`get`, `list`) are not locked and may be called concurrently.

**Not** covered by that lock, despite being mutating calls: `orders.cancel()` (a real gap — the other `OrderAPI` methods take the lock, this one doesn't), and everything on `notes` and `runner`/`replay` (`NoteAPI` and `RunnerAPI` are constructed without any lock at all). Don't call those concurrently on a shared `Phantom` instance from multiple threads without your own external locking.

```python
import threading
from phantom import Phantom

ph = Phantom(data_dir="./data")   # one shared instance

def worker(ticker):
    account = ph.accounts.get("shared-account")
    ph.orders.place(account_id=account.id, order=Order(...))

threads = [threading.Thread(target=worker, args=(t,)) for t in ["AAPL", "MSFT"]]
for t in threads:
    t.start()
for t in threads:
    t.join()
```
