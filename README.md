# Phantom Ledger

A local-first Python paper trading and backtesting engine. Works as both a library and a CLI tool — no cloud account required, no data leaves your machine.

```python
from phantom import Phantom
```
```bash
phantom order place --account my-account --ticker AAPL --direction long --type market --quantity 10
```

---

## Features

- **Backtesting** — run strategies against historical OHLCV data with realistic cost simulation
- **Paper trading** — live forward-testing loop against Yahoo Finance / Alpaca, with optional APScheduler integration and systemd service generation
- **Cost engine** — commission (fixed, per-share, tiered, zero), spread, slippage, overnight/swap, FX conversion, dividend adjustments
- **Broker profiles** — bundled DEGIRO, IBKR, XTB profiles; load any custom JSON profile
- **Order types** — market, limit, stop, stop-limit, trailing stop, OCO
- **Margin engine** — margin call and stop-out cascade for CFD positions
- **Position replay** — reapply the simulation engine to closed positions for post-trade analysis
- **Reporting** — equity curve, CAGR, max drawdown, Sharpe, Sortino, win rate, broker cost comparison, CSV export, terminal chart
- **Trade notes** — markdown notes attached to positions, full-text search
- **Web UI** — embedded dashboard with HTMX live updates (no JavaScript framework)
- **Thread-safe library API** — multiple `Phantom` instances can coexist; all mutating operations are lock-protected

---

## Install

### As a dependency

```bash
uv add phantom-ledger
# or
pip install phantom-ledger
```

### From source

```bash
git clone --recurse-submodules git@github.com:best-testing-monkey/phantom_ledger.git
cd phantom_ledger
uv sync
```

> The `--recurse-submodules` flag is required to pull the `price_cache` data submodule.

### Development (tests + linter)

```bash
uv sync --extra dev
uv run pytest
uv run ruff check src/ tests/
```

---

## Configuration

| Environment variable | Default  | Description                                             |
|----------------------|----------|---------------------------------------------------------|
| `PHANTOM_DATA`       | `./data` | Root directory for SQLite DB, price cache, notes        |

A `.env` file in the working directory is loaded automatically.

---

## Backtesting

### As a library

```python
from phantom import Phantom

ph = Phantom(data_dir="./data")

# Create an account backed by the IBKR cost profile
account = ph.accounts.create(
    name="backtest-1",
    account_type="manual",
    broker="IBKR",
    capital=10_000.0,
    currency="USD",
)

# Pre-fetch price data (optional — the engine fetches on demand)
ph.data.fetch_prices("AAPL", start="2023-01-01", end="2023-12-31")

# Run the backtest
result = ph.runner.backtest(
    account_id=account.id,
    tickers=["AAPL"],
    start="2023-01-01",
    end="2023-12-31",
)

m = result.equity_metrics
t = result.trade_metrics
print(f"Return:       {m.total_return_pct:+.2f}%")
print(f"CAGR:         {m.cagr_pct:.2f}%")
print(f"Max drawdown: {m.max_drawdown_pct:.2f}%")
print(f"Sharpe:       {m.sharpe_ratio:.2f}")
print(f"Trades:       {t.trade_count}  Win rate: {t.win_rate_pct:.1f}%")
```

#### With a custom strategy

Supply an `on_bar` callback — it receives the current OHLCV bar, the account state, and open positions, and returns a list of orders to place:

```python
from phantom import Phantom, Order

ph = Phantom(data_dir="./data")
account = ph.accounts.create(
    name="sma-cross",
    account_type="algorithm",
    broker="DEGIRO",
    capital=5_000.0,
    currency="EUR",
    algorithm_id="sma_cross",
)

closes: list[float] = []

def on_bar(bar, account, positions):
    closes.append(bar["Close"])
    if len(closes) < 21:
        return []

    fast = sum(closes[-10:]) / 10
    slow = sum(closes[-20:]) / 20
    prev_fast = sum(closes[-11:-1]) / 10
    prev_slow = sum(closes[-21:-1]) / 20

    open_longs = [p for p in positions if p.direction == "long" and p.status == "open"]

    # Golden cross — go long
    if prev_fast <= prev_slow and fast > slow and not open_longs:
        return [Order(
            account_id=account.id,
            ticker="MSFT",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
            take_profit=bar["Close"] * 1.05,
            stop_loss=bar["Close"] * 0.97,
        )]

    # Death cross — close long
    if prev_fast >= prev_slow and fast < slow and open_longs:
        return [Order(
            account_id=account.id,
            ticker="MSFT",
            instrument_type="stock",
            direction="long",
            order_type="market",
            quantity=10,
        )]

    return []

result = ph.runner.backtest(
    account_id=account.id,
    tickers=["MSFT"],
    start="2022-01-01",
    end="2023-12-31",
    on_bar=on_bar,
)
```

> **Note:** The `phantom run backtest` CLI command is a placeholder. Use the library API for backtesting.

---

## Paper Trading (Forward Testing)

### Via CLI

```bash
# Create an account
phantom account create \
    --name live-paper \
    --type manual \
    --broker IBKR \
    --capital 10000 \
    --currency USD

# Start the paper trading loop (blocks; Ctrl-C to stop)
phantom run --account live-paper --ticker AAPL --interval 300

# Or install as a background systemd user service
phantom service install --account live-paper --interval 300
systemctl --user start phantom-live-paper
```

The loop ticks every `--interval` seconds, fetches the latest bar, fills pending orders, accrues overnight costs, and checks margin levels.

### As a library — blocking loop

```python
import threading
from phantom import Phantom

ph = Phantom(data_dir="./data")
account = ph.accounts.get("live-paper")

stop = threading.Event()

# Runs until stop.set() is called, or SIGINT / SIGTERM
ph.runner.paper_trade(
    account_id=account.id,
    tickers=["AAPL", "MSFT"],
    interval=300,
    stop_event=stop,
)
```

### As a library — non-blocking background handle

```python
from phantom import Phantom

ph = Phantom(data_dir="./data")
account = ph.accounts.get("live-paper")

handle = ph.runner.paper_trade_background(
    account_id=account.id,
    tickers=["AAPL", "MSFT"],
    interval=300,
)

print("Running:", handle.is_running())

# ... rest of your application ...

handle.stop()
```

---

## Web UI

```bash
phantom web serve --port 8080
```

Opens a dashboard at `http://localhost:8080` with live equity snapshots (HTMX poll every 30 s), open position table, recent closed trades, and a broker cost comparison page.

---

## Documentation

- **[CLI reference](docs/cli.md)** — every command, argument, and option
- **[Library reference](docs/library.md)** — complete API with examples

---

## Bundled broker profiles

| Profile | Commission type        | Overnight   | Leverage | Base currency |
|---------|------------------------|-------------|----------|---------------|
| DEGIRO  | Per-share              | No          | 1×       | EUR           |
| IBKR    | Tiered                 | Yes (SOFR+) | 4×       | USD + majors  |
| XTB     | Zero (monthly cap)     | Yes         | 20×      | EUR           |

Load a custom profile:

```bash
phantom broker validate my-broker.json
```

```python
ph.brokers.load_from_file("my-broker.json")
account = ph.accounts.create(name="test", broker="my-broker", ...)
```

---

## License

MIT
