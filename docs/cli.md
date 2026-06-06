# CLI Reference

The `phantom` command is the entry point. Every sub-command follows the same pattern:

```
phantom <group> <command> [options]
```

All commands read `PHANTOM_DATA` (default: `./data`) for the database location. A `.env` file in the working directory is loaded automatically.

---

## Global help

```bash
phantom --help
phantom <group> --help
phantom <group> <command> --help
```

---

## `account` — Manage accounts

### `account create`

Create a new trading account.

```bash
phantom account create \
    --name NAME \
    --type {pattern|manual|algorithm|aggregate} \
    --broker BROKER \
    --capital FLOAT \
    [--currency EUR] \
    [--pattern-tag TAG] \
    [--algorithm-id ID] \
    [--algorithm-version VER] \
    [--children "child1,child2"]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--name` | Yes | Unique account name |
| `--type` | Yes | `manual` (human), `pattern` (rule-based), `algorithm` (automated), `aggregate` (rollup of children) |
| `--broker` | Yes | Broker profile name (e.g. `IBKR`, `DEGIRO`, `XTB`) |
| `--capital` | Yes | Starting cash balance |
| `--currency` | No | ISO 4217 base currency (default: `EUR`) |
| `--pattern` | No | Pattern tag — required when `--type pattern` |
| `--algorithm-id` | No | Algorithm identifier string |
| `--algorithm-version` | No | Algorithm version string |
| `--children` | No | Comma-separated child account names — required when `--type aggregate` |

```bash
# Simple manual account
phantom account create --name my-account --type manual --broker IBKR \
    --capital 10000 --currency USD

# Algorithm account
phantom account create --name algo-v2 --type algorithm --broker DEGIRO \
    --capital 5000 --algorithm-id sma_cross --algorithm-version 2.1

# Aggregate rollup
phantom account create --name portfolio --type aggregate --broker IBKR \
    --capital 0 --children "algo-v2,my-account"
```

---

### `account list`

List all accounts with cash balance, type, and broker.

```bash
phantom account list
```

---

### `account show`

Show full account details including margin summary for CFD accounts.

```bash
phantom account show NAME
```

---

### `account delete`

Delete an account and all its positions. Prompts for confirmation unless `--yes` is supplied.

```bash
phantom account delete NAME [--yes]
```

---

## `order` — Place and manage orders

### `order place`

Place an order on an account.

```bash
phantom order place \
    --account ACCOUNT \
    --ticker TICKER \
    --direction {long|short} \
    --type {market|limit|stop|stop_limit|trailing_stop|oco} \
    --quantity FLOAT \
    [--instrument {stock|cfd}] \
    [--limit-price FLOAT] \
    [--stop-price FLOAT] \
    [--trailing-amount FLOAT] \
    [--trailing-pct FLOAT] \
    [--tp FLOAT] \
    [--sl FLOAT] \
    [--at DATETIME] \
    [--good-til DATETIME]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--account` | Yes | Account name |
| `--ticker` | Yes | Ticker symbol (e.g. `AAPL`) |
| `--direction` | Yes | `long` or `short` |
| `--type` | Yes | Order type |
| `--quantity` | Yes | Number of shares / contracts |
| `--instrument` | No | `stock` (default) or `cfd` |
| `--limit-price` | No | Required for `limit` and `stop_limit` orders |
| `--stop-price` | No | Required for `stop`, `stop_limit`, and `oco` orders |
| `--trailing-amount` | No | Absolute trailing distance (for `trailing_stop`) |
| `--trailing-pct` | No | Percentage trailing distance (for `trailing_stop`) |
| `--tp` | No | Take-profit price |
| `--sl` | No | Stop-loss price |
| `--at` | No | Historical creation datetime (ISO 8601) — for replay |
| `--good-til` | No | Order expiry datetime (ISO 8601) |

```bash
# Market order with TP/SL
phantom order place --account my-account --ticker AAPL \
    --direction long --type market --quantity 10 \
    --tp 185.00 --sl 170.00

# Limit order
phantom order place --account my-account --ticker MSFT \
    --direction long --type limit --quantity 5 --limit-price 380.00

# Trailing stop
phantom order place --account my-account --ticker TSLA \
    --direction long --type trailing_stop --quantity 3 --trailing-pct 3.0

# Short CFD
phantom order place --account my-account --ticker SPY \
    --direction short --type market --quantity 50 --instrument cfd
```

---

### `order list`

List orders for an account, optionally filtered by status.

```bash
phantom order list --account ACCOUNT [--status {pending|triggered|filled|expired|rejected|cancelled}]
```

---

### `order cancel`

Cancel a pending order.

```bash
phantom order cancel ORDER_ID
```

---

## `position` — Manage positions

### `position list`

List positions, optionally filtered by account and status. CFD positions include a "Margin Req." column.

```bash
phantom position list [--account ACCOUNT] [--status {open|closed|liquidated}]
```

---

### `position show`

Show all fields for a single position including cost breakdown.

```bash
phantom position show POSITION_ID
```

---

### `position close`

Manually close an open position at a specified exit price.

```bash
phantom position close POSITION_ID --price FLOAT [--reason {tp|sl|trailing_stop|max_time|margin_call|manual}] [--yes]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--price` | Yes | Exit price |
| `--reason` | No | Close reason (default: `manual`) |
| `--yes` | No | Skip confirmation prompt |

---

### `position modify`

Update the take-profit and/or stop-loss on an open position.

```bash
phantom position modify POSITION_ID [--tp FLOAT] [--sl FLOAT]
```

At least one of `--tp` or `--sl` must be supplied.

---

## `note` — Trade notes

Notes are markdown files stored under `$PHANTOM_DATA/notes/`.

### `note add`

Add a note to a position. Opens `$EDITOR` when `--file` is not supplied.

```bash
phantom note add POSITION_ID --title "Entry rationale" [--file path/to/note.md]
```

### `note list`

List all notes attached to a position.

```bash
phantom note list POSITION_ID
```

### `note show`

Print the raw markdown content of a note to stdout (pipe-friendly).

```bash
phantom note show NOTE_ID
phantom note show NOTE_ID > analysis.md
```

### `note edit`

Edit a note in `$EDITOR`.

```bash
phantom note edit NOTE_ID
```

### `note search`

Full-text search across all notes for an account.

```bash
phantom note search ACCOUNT_NAME "keyword"
```

---

## `report` — Performance reports

### `report show`

Display a performance report for an account.

```bash
phantom report show \
    --account ACCOUNT \
    [--pattern TAG] \
    [--algo-version VER] \
    [--aggregate] \
    [--compare-brokers "IBKR,DEGIRO,XTB"] \
    [--export-csv path/to/equity.csv] \
    [--chart]
```

| Option | Description |
|--------|-------------|
| `--account` | Account name (required) |
| `--pattern` | Filter positions by pattern tag |
| `--algo-version` | Filter positions by algorithm version |
| `--aggregate` | Roll up all child accounts into a single combined report |
| `--compare-brokers` | Comma-separated broker names — shows side-by-side cost comparison |
| `--export-csv` | Write equity curve to a CSV file (columns: timestamp, equity, drawdown_pct) |
| `--chart` | Render equity curve in the terminal using plotext (requires `pip install phantom-ledger[charts]`) |

```bash
# Basic report
phantom report show --account my-account

# Aggregate with broker comparison and chart
phantom report show --account portfolio --aggregate \
    --compare-brokers "IBKR,DEGIRO" --chart

# Export equity curve
phantom report show --account algo-v2 --export-csv results/equity.csv
```

---

## `data` — Market data

### `data fetch`

Fetch and cache historical OHLCV data for a ticker.

```bash
phantom data fetch --ticker AAPL --start 2023-01-01 [--end 2024-01-01]
```

`--end` defaults to today. Data is stored in the `price_cache` SQLite database.

### `data fetch-rates`

Fetch and cache reference interest rates (used for overnight cost calculations).

```bash
phantom data fetch-rates --rate {SOFR|ESTR} --start 2023-01-01 [--end 2024-01-01]
```

---

## `broker` — Broker profiles

### `broker list`

List all loaded broker profiles.

```bash
phantom broker list
```

### `broker show`

Show the full configuration of a broker profile.

```bash
phantom broker show IBKR
```

### `broker validate`

Validate a custom broker profile JSON file before using it.

```bash
phantom broker validate path/to/my-broker.json
```

---

## `run` — Paper trading loop

Start a live paper trading loop (blocking).

```bash
phantom run \
    --account ACCOUNT \
    [--ticker TICKER] \
    [--interval 300] \
    [--mode paper] \
    [--scheduler]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--account` | (required) | Account name |
| `--ticker` | — | Primary ticker to monitor |
| `--interval` | `300` | Seconds between ticks |
| `--mode` | `paper` | `paper` for live simulation |
| `--scheduler` | `False` | Use APScheduler (market-hours aware) instead of a simple blocking loop |

```bash
# Simple 5-minute loop
phantom run --account live-paper --ticker AAPL --interval 300

# Market-hours-aware scheduler
phantom run --account live-paper --ticker AAPL --interval 300 --scheduler
```

Press `Ctrl-C` to stop gracefully.

> The `phantom run backtest` sub-command is reserved for future use. Use the [library API](library.md#backtesting) for backtesting.

---

## `replay` — Historical replay

Replay the simulation engine over already-closed positions to reconstruct cost breakdowns and metrics.

### `replay all`

Replay all un-replayed positions for an account.

```bash
phantom replay all --account ACCOUNT
```

### `replay single`

Replay a single position by ID. Use `--force` to re-run a position that was already replayed.

```bash
phantom replay single --position POSITION_ID [--force]
```

---

## `service` — systemd integration

### `service install`

Generate and install a systemd user service that runs the paper trading loop in the background.

```bash
phantom service install --account ACCOUNT [--interval 300]
```

This writes `~/.config/systemd/user/phantom-{account}.service`. After installation:

```bash
systemctl --user daemon-reload
systemctl --user enable phantom-live-paper
systemctl --user start phantom-live-paper
systemctl --user status phantom-live-paper
journalctl --user -u phantom-live-paper -f
```

---

## `web` — Web UI

### `web serve`

Start the embedded FastAPI / HTMX dashboard.

```bash
phantom web serve [--port 8080]
```

The server binds to `0.0.0.0:{port}`. Open `http://localhost:{port}` in a browser.

Pages:

| Route | Description |
|-------|-------------|
| `/` | Dashboard — account summary, open positions, recent closed trades |
| `/positions/{id}` | Position detail with full cost breakdown and notes |
| `/orders/new` | Order placement form |
| `/brokers/compare?account=NAME` | Side-by-side broker cost comparison |
| `/api/equity-snapshot?account=NAME` | HTMX fragment (equity panel, refreshed every 30 s) |
| `/api/positions-rows?account=NAME` | HTMX fragment (positions table rows) |
