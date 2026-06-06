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

Multiple instances can coexist. All mutating operations acquire an internal `threading.RLock`, so it is safe to share a single `Phantom` instance across threads.

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

Raises `ValidationError` if `name` already exists.

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

Deletes the account and all its positions. Irreversible.

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
filled_order = ph.orders.place(account_id: str, order: Order) -> Order
```

Validates broker support for the instrument type and direction, deducts margin for CFDs, and either fills the order immediately (market) or queues it as pending. Raises `ValidationError`, `InsufficientFundsError`, or `MarginError` on failure.

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

### `cancel`

```python
cancelled = ph.orders.cancel(order_id: str) -> Order
```

Raises `ValidationError` if the order is not in `pending` status.

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

When `account_name` is `None`, returns all open positions across all accounts.

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
) -> Position
```

Raises `ValidationError` if position is not open or `exit_price` is not supplied.

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
    on_bar=None,              # strategy callback (see below)
) -> BacktestResult
```

`BacktestResult` attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `.equity_metrics` | `EquityMetrics` | Return, CAGR, drawdown, Sharpe, Sortino |
| `.trade_metrics` | `TradeMetrics` | Trade count, win rate, profit factor, expectancy |
| `.positions` | `list[Position]` | All positions opened during the run |
| `.equity_curve` | `list[EquityPoint]` | Per-bar equity snapshots |

#### Strategy callback

```python
def on_bar(bar: dict, account: Account, positions: list[Position]) -> list[Order]:
    ...
```

`bar` keys: `"Open"`, `"High"`, `"Low"`, `"Close"`, `"Volume"`, `"datetime"` (UTC).

Return an empty list to do nothing, or a list of `Order` objects to place. Orders are evaluated against the current bar before moving to the next.

```python
result = ph.runner.backtest(
    account_id=account.id,
    tickers=["AAPL"],
    start="2023-01-01",
    end="2023-12-31",
    on_bar=my_strategy,
)
print(f"Sharpe: {result.equity_metrics.sharpe_ratio:.2f}")
print(f"Trades: {result.trade_metrics.trade_count}")
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

# Search across all notes for an account
from phantom.notes.manager import SearchResult

results: list[SearchResult] = ph.notes.search(account_id=account.id, keyword="golden cross")
# SearchResult.note_id, SearchResult.title, SearchResult.snippet
```

---

## `ph.data` — `DataAPI`

```python
# Fetch and cache OHLCV data (uses price_cache SQLite backend)
df = ph.data.fetch_prices(
    ticker: str,
    start: str | datetime,   # "YYYY-MM-DD" or datetime
    end: str | datetime,
) -> pd.DataFrame            # DatetimeIndex (UTC), columns: Open/High/Low/Close/Volume

# Fetch and cache a reference rate
rates = ph.data.fetch_rates(
    rate: str,               # "SOFR" or "ESTR" (case-insensitive)
    start: str | datetime,
    end: str | datetime,
) -> pd.Series
```

Both methods raise `DataError` on network failure.

---

## `ph.brokers` — `BrokerAPI`

```python
# List bundled profiles
profiles = ph.brokers.list() -> list[BrokerProfile]

# Get a profile by name
profile = ph.brokers.get("IBKR") -> BrokerProfile

# Load a custom JSON profile from disk
profile = ph.brokers.load_from_file("path/to/my-broker.json") -> BrokerProfile
```

Raises `NotFoundError` when a named profile does not exist. Raises `ProfileError` on malformed JSON.

---

## `ph.reports` — `ReportAPI`

```python
from phantom.reports.metrics import EquityMetrics, TradeMetrics, CostSummary, EquityPoint

# Compute equity metrics from an equity curve
metrics: EquityMetrics = ph.reports.equity_metrics(account_name)

# Compute trade metrics from closed positions
trade_metrics: TradeMetrics = ph.reports.trade_metrics(account_name)

# Aggregate cost summary across all positions
costs: CostSummary = ph.reports.cost_summary(account_name)

# Export equity curve to CSV
rows_written = ph.reports.export_csv(account_name, path="equity.csv")

# Compare costs across broker profiles
comparison: dict[str, CostSummary] = ph.reports.compare_brokers(
    account_name, profile_names=["IBKR", "DEGIRO", "XTB"]
)
```

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
    overnight: float
    fx: float
    dividend: float
    total: float
```

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
    unrealized_pnl: float              # @computed_field; 0.0 for closed positions
```

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

Use `in_memory=True` to get a throwaway SQLite database — no file created, no cleanup needed.

```python
import pytest
from phantom import Phantom

@pytest.fixture
def ph():
    return Phantom(data_dir="./data", in_memory=True)

def test_place_order(ph):
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
    assert order.status == "filled"
```

Never mock the database — use the in-memory fixture instead. Mock only external HTTP calls (price fetches, rate fetches) with `unittest.mock.patch`.

---

## Thread safety

All mutating operations (`accounts.create`, `accounts.delete`, `orders.place`, `orders.cancel`, `positions.close`, `positions.modify`) are protected by an internal `threading.RLock`. Read operations (`get`, `list`) are not locked and may be called concurrently.

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
