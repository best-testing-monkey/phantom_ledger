# Phantom Ledger — Implementation Order

Stories ordered by the dependency graph in `phantom-ledger-architecture.md` Section 10.
Check off each story as it is completed.

---

## MVP

### E1 · Project Scaffolding
> Everything depends on this. Do it first.

- [x] E1-S01 — [Initialize uv project with pyproject.toml, src layout, and test directory](tickets/e01-s01.md)
- [x] E1-S02 — [Set up SQLite database module with connection pooling and WAL mode](tickets/e01-s02.md)
- [x] E1-S03 — [Implement migration runner](tickets/e01-s03.md)
- [x] E1-S04 — [Write 001_initial.sql (all MVP tables)](tickets/e01-s04.md)
- [x] E1-S05 — [Create api/ module skeleton: Phantom facade, sub-API stubs, exception hierarchy](tickets/e01-s05.md)
- [x] E1-S06 — [Create Typer CLI skeleton with all subcommand groups](tickets/e01-s06.md)
- [x] E1-S07 — [Implement config module](tickets/e01-s07.md)
- [x] E1-S08 — [Set up pytest fixtures](tickets/e01-s08.md)
- [x] E1-S09 — [Configure ruff](tickets/e01-s09.md)

---

### E2 · Broker Profile System (core)
> Needed by E3 (cost engine) and everything that touches broker profiles.

- [x] E2-S01 — [Define BrokerProfile Pydantic model with all sub-models](tickets/e02-s01.md)
- [x] E2-S02 — [Implement JSON loader](tickets/e02-s02.md)
- [x] E2-S03 — [Write DEGIRO broker profile JSON](tickets/e02-s03.md)
- [x] E2-S04 — [Implement broker_repo](tickets/e02-s04.md)
- [x] E2-S05 — [CLI: `phantom broker list` and `phantom broker show`](tickets/e02-s05.md)

### E3 · Cost Engine (MVP)
> Depends on E2. Needed by E6 (order fills).

- [x] E3-S01 — [CommissionModel: "fixed" type](tickets/e03-s01.md)
- [x] E3-S02 — [SpreadModel: "fixed" and "dynamic" types](tickets/e03-s02.md)
- [x] E3-S03 — [SlippageModel: "fixed_pct" type](tickets/e03-s03.md)
- [x] E3-S04 — [CostEngine: compose sub-models, entry_costs() / exit_costs() → CostBreakdown](tickets/e03-s04.md)
- [x] E3-S05 — [Unit tests: commission, spread, slippage](tickets/e03-s05.md)

---

### E4 · Data Layer
> Depends on E1. Needed by E9 (simulation loop reads prices).

- [x] E4-S01 — [HistoricalProvider: yfinance fetch + Parquet cache](tickets/e04-s01.md)
- [x] E4-S02 — [Parquet cache management (freshness, append, splits)](tickets/e04-s02.md)
- [x] E4-S03 — [CLI: `phantom data fetch`](tickets/e04-s03.md)
- [x] E4-S04 — [DataProvider protocol + HistoricalProvider conformance](tickets/e04-s04.md)

---

### E5 · Account System
> Depends on E1. Needed by E6 (orders belong to accounts).

- [x] E5-S01 — [Account model (Pydantic) with account_type enum](tickets/e05-s01.md)
- [x] E5-S02 — [account_repo: CRUD in SQLite](tickets/e05-s02.md)
- [x] E5-S03 — [CLI: `phantom account create`](tickets/e05-s03.md)
- [x] E5-S04 — [CLI: `phantom account list` / `phantom account show`](tickets/e05-s04.md)

### E6 · Order System
> Depends on E5 (accounts) and E3 (costs on fill).

- [x] E6-S01 — [Order model with all fields](tickets/e06-s01.md)
- [x] E6-S02 — [order_repo](tickets/e06-s02.md)
- [x] E6-S03 — [OrderManager.place(): validate + persist as "pending"](tickets/e06-s03.md)
- [x] E6-S04 — [OrderManager.evaluate(): trigger/fill on each bar](tickets/e06-s04.md)
- [x] E6-S05 — [On fill: compute entry costs, deduct cash, create Position, link order](tickets/e06-s05.md)
- [x] E6-S06 — [Order expiry (good_til)](tickets/e06-s06.md)
- [x] E6-S07 — [CLI: `phantom order place`](tickets/e06-s07.md)
- [x] E6-S08 — [CLI: `phantom order list` / `phantom order cancel`](tickets/e06-s08.md)

### E7 · Position System
> Depends on E6.

- [x] E7-S01 — [Position model with all fields](tickets/e07-s01.md)
- [ ] E7-S02 — [position_repo](tickets/e07-s02.md)
- [ ] E7-S03 — [PositionManager.update(): unrealized P&L, TP/SL check](tickets/e07-s03.md)
- [ ] E7-S04 — [TP/SL exit logic (trigger price, exit costs, close_reason)](tickets/e07-s04.md)
- [ ] E7-S05 — [TP/SL ambiguity handling (conservative / optimistic / proximity)](tickets/e07-s05.md)
- [ ] E7-S06 — [max_close_datetime auto-close](tickets/e07-s06.md)
- [ ] E7-S07 — [Manual close CLI: `phantom position close`](tickets/e07-s07.md)
- [ ] E7-S08 — [Position modify CLI: `phantom position modify`](tickets/e07-s08.md)
- [ ] E7-S09 — [CLI: `phantom position list` / `phantom position show`](tickets/e07-s09.md)

### E9 · Simulation Engine (MVP)
> Depends on E7 (position updates) and E4 (price data).

- [ ] E9-S01 — [BacktestClock: step through DatetimeIndex](tickets/e09-s01.md)
- [ ] E9-S02 — [SimulationEngine.run_backtest(): bar loop → evaluate orders → update positions](tickets/e09-s02.md)
- [ ] E9-S03 — [Equity curve recording per bar](tickets/e09-s03.md)
- [ ] E9-S04 — [Integration test: market order with TP/SL, full backtest run, verify outcome](tickets/e09-s04.md)

### E10 · Historical Position Replay (MVP)
> Depends on E9.

- [ ] E10-S01 — [ReplayEngine.replay_position(): load bars, run lifecycle](tickets/e10-s01.md)
- [ ] E10-S02 — [Replay outcome handling (historical close vs. still open)](tickets/e10-s02.md)
- [ ] E10-S03 — [CLI: `phantom replay --account <name>`](tickets/e10-s03.md)
- [ ] E10-S04 — [CLI: `phantom replay --position <id>`](tickets/e10-s04.md)
- [ ] E10-S05 — [Replay idempotency (replay_completed_at, prevent double-replay)](tickets/e10-s05.md)

---

### E11 · Trade Notes
> Depends on E1 only (filesystem + DB). Can be done in parallel with E4–E10.

- [ ] E11-S01 — [NoteManager: create file + metadata row](tickets/e11-s01.md)
- [ ] E11-S02 — [Note creation from file](tickets/e11-s02.md)
- [ ] E11-S03 — [Note creation via $EDITOR](tickets/e11-s03.md)
- [ ] E11-S04 — [CLI: `phantom note list`](tickets/e11-s04.md)
- [ ] E11-S05 — [CLI: `phantom note show`](tickets/e11-s05.md)
- [ ] E11-S06 — [Note size tracking](tickets/e11-s06.md)

---

### E12 · Reporting (MVP)
> Depends on E1 (DB). Meaningful output requires closed positions, but the calculator can be built earlier.

- [ ] E12-S01 — [Metrics calculator: total return, CAGR, max drawdown, drawdown duration](tickets/e12-s01.md)
- [ ] E12-S02 — [Trade-level metrics: win rate, avg win/loss, profit factor, expectancy](tickets/e12-s02.md)
- [ ] E12-S03 — [Cost breakdown aggregation across closed positions](tickets/e12-s03.md)
- [ ] E12-S04 — [CLI: `phantom report --account <name>`](tickets/e12-s04.md)

---

### E17 · Library API Surface + CLI Wiring (MVP)
> Final MVP integration step. Each sub-API (S03–S10) is built as its underlying epic completes; S11–S12 are the final wire-up.

- [ ] E17-S01 — [PhantomError exception hierarchy](tickets/e17-s01.md)
- [ ] E17-S02 — [Phantom facade class (data_dir, in_memory, sub-API attributes)](tickets/e17-s02.md)
- [ ] E17-S03 — [AccountAPI: create(), list(), get(), delete()](tickets/e17-s03.md)
- [ ] E17-S04 — [BrokerAPI: load(), list(), get(), validate()](tickets/e17-s04.md)
- [ ] E17-S05 — [OrderAPI: place(), list(), cancel()](tickets/e17-s05.md)
- [ ] E17-S06 — [PositionAPI: list(), get(), close(), modify()](tickets/e17-s06.md)
- [ ] E17-S07 — [NoteAPI: add(), add_from_file(), list(), get()](tickets/e17-s07.md)
- [ ] E17-S08 — [RunnerAPI: replay(), replay_position(), backtest()](tickets/e17-s08.md)
- [ ] E17-S09 — [DataAPI: fetch_prices(), fetch_rates()](tickets/e17-s09.md)
- [ ] E17-S10 — [ReportAPI: account_metrics(), cost_breakdown()](tickets/e17-s10.md)
- [ ] E17-S11 — [`phantom/__init__.py` public re-exports](tickets/e17-s11.md)
- [ ] E17-S12 — [CLI refactor: strip all logic, every command is a thin wrapper](tickets/e17-s12.md)

---

## P2

### E2 · Broker Profiles (remaining)

- [ ] E2-S06 — [IBKR broker profile JSON](tickets/e02-s06.md)
- [ ] E2-S07 — [XTB broker profile JSON](tickets/e02-s07.md)
- [ ] E2-S08 — [CLI: `phantom broker validate <file>`](tickets/e02-s08.md)

### E3 · Cost Engine (full)
> Adds overnight, FX, dividends. Needed by E9-S09/S10 hooks.

- [ ] E3-S06 — [CommissionModel: "per_share" and "tiered" types](tickets/e03-s06.md)
- [ ] E3-S07 — [CommissionModel: "zero" type (monthly free volume)](tickets/e03-s07.md)
- [ ] E3-S08 — [SlippageModel: "volume_based" type](tickets/e03-s08.md)
- [ ] E3-S09 — [SpreadModel: "market" mode (live bid/ask override)](tickets/e03-s09.md)
- [ ] E3-S10 — [OvernightModel.calculate(): reference rate + markup, triple swap day](tickets/e03-s10.md)
- [ ] E3-S11 — [FX conversion cost](tickets/e03-s11.md)
- [ ] E3-S12 — [DividendModel: stock withholding by country](tickets/e03-s12.md)
- [ ] E3-S13 — [DividendModel: CFD dividend adjustment](tickets/e03-s13.md)
- [ ] E3-S14 — [Unit tests: overnight, FX, dividend](tickets/e03-s14.md)

### E4 · Data Layer (remaining)
> Dividends + rates needed by overnight/dividend hooks; LiveProvider needed by paper trade loop.

- [ ] E4-S05 — [Dividend data fetching (yfinance ex-dates + amounts, cached)](tickets/e04-s05.md)
- [ ] E4-S06 — [Reference rate fetcher: SOFR (NY Fed), ESTR (ECB SDMX)](tickets/e04-s06.md)
- [ ] E4-S07 — [CLI: `phantom data fetch-rates`](tickets/e04-s07.md)
- [ ] E4-S08 — [LiveProvider: real-time price + bid/ask](tickets/e04-s08.md)
- [ ] E4-S09 — [Data staleness detection for paper-trade mode](tickets/e04-s09.md)

### E5 · Account System (remaining)

- [ ] E5-S05 — [Aggregate account computation (sum child equity curves)](tickets/e05-s05.md)
- [ ] E5-S06 — [Account-level margin tracking (used_margin, free_margin, margin_level)](tickets/e05-s06.md)
- [ ] E5-S07 — [Validation: reject CFD/short on non-CFD broker profiles](tickets/e05-s07.md)
- [ ] E5-S08 — [CLI: `phantom account delete` with confirmation + cascade warning](tickets/e05-s08.md)

### E6 · Order System (remaining)

- [ ] E6-S09 — [Stop order](tickets/e06-s09.md)
- [ ] E6-S10 — [Stop-Limit order](tickets/e06-s10.md)
- [ ] E6-S11 — [Trailing Stop order](tickets/e06-s11.md)
- [ ] E6-S12 — [OCO (One-Cancels-Other)](tickets/e06-s12.md)
- [ ] E6-S13 — [Margin validation on order placement](tickets/e06-s13.md)
- [ ] E6-S14 — [Order rejection reasons (funds, margin, hours, instrument)](tickets/e06-s14.md)

### E7 · Position System (remaining)

- [ ] E7-S10 — [Trailing stop tracking per bar](tickets/e07-s10.md)
- [ ] E7-S11 — [Overnight cost accrual per day boundary](tickets/e07-s11.md)
- [ ] E7-S12 — [overnight_log table persistence](tickets/e07-s12.md)
- [ ] E7-S13 — [Dividend processing on ex-date](tickets/e07-s13.md)
- [ ] E7-S14 — [dividend_log table persistence](tickets/e07-s14.md)
- [ ] E7-S15 — [Margin tracking per position](tickets/e07-s15.md)
- [ ] E7-S16 — [Stock vs CFD behavior (overnight/leverage/margin gating)](tickets/e07-s16.md)

### E8 · Margin Engine
> Depends on E7-S15 (per-position margin). Needed by E9-S11 and E10-S07.

- [ ] E8-S01 — [MarginEngine.check(): margin_level, return ok/margin_call/stop_out](tickets/e08-s01.md)
- [ ] E8-S02 — [Margin call warning: log, flag, persist timestamp](tickets/e08-s02.md)
- [ ] E8-S03 — [Stop-out cascade: force-close largest loser until recovered](tickets/e08-s03.md)
- [ ] E8-S04 — [Integration test: CFD stop-out cascade](tickets/e08-s04.md)
- [ ] E8-S05 — [Margin level display in `account show` and `position list`](tickets/e08-s05.md)

### E9 · Simulation Engine (remaining)
> Depends on E8 (margin hook), E3-S10 (overnight), E4-S05/S06 (dividends/rates).

- [ ] E9-S05 — [LiveClock: wall-clock time, advance() blocks until next tick](tickets/e09-s05.md)
- [ ] E9-S06 — [SimulationEngine.run_paper(): LiveClock + LiveProvider loop](tickets/e09-s06.md)
- [ ] E9-S07 — [CLI: `phantom run --mode paper --interval 300`](tickets/e09-s07.md)
- [ ] E9-S08 — [Graceful shutdown (SIGINT/SIGTERM)](tickets/e09-s08.md)
- [ ] E9-S09 — [Overnight cost accrual hook in loop](tickets/e09-s09.md)
- [ ] E9-S10 — [Dividend hook in loop](tickets/e09-s10.md)
- [ ] E9-S11 — [Margin check hook in loop](tickets/e09-s11.md)

### E10 · Replay (remaining)
> Depends on E9-S09/S10 (overnight/dividend) and E8-S01 (margin).

- [ ] E10-S06 — [Replay with overnight + dividend hooks](tickets/e10-s06.md)
- [ ] E10-S07 — [Replay with margin simulation](tickets/e10-s07.md)
- [ ] E10-S08 — [Performance: share price data load across positions for same ticker](tickets/e10-s08.md)

### E11 · Trade Notes (remaining)

- [ ] E11-S07 — [Note edit via $EDITOR](tickets/e11-s07.md)
- [ ] E11-S08 — [Note search (grep across account notes)](tickets/e11-s08.md)

### E12 · Reporting (remaining)

- [ ] E12-S05 — [Sharpe ratio and Sortino ratio](tickets/e12-s05.md)
- [ ] E12-S06 — [Per-pattern-tag filtering](tickets/e12-s06.md)
- [ ] E12-S07 — [Per-algorithm-version filtering](tickets/e12-s07.md)
- [ ] E12-S08 — [Aggregate account reporting (combined equity curves)](tickets/e12-s08.md)
- [ ] E12-S09 — [Cost comparison across broker profiles](tickets/e12-s09.md)
- [ ] E12-S10 — [CLI: `phantom report --compare-brokers`](tickets/e12-s10.md)
- [ ] E12-S11 — [Export equity curve to CSV](tickets/e12-s11.md)

### E13 · Paper Trade Scheduler
> Depends on E9-S06 (run_paper loop).

- [ ] E13-S01 — [APScheduler integration: interval trigger](tickets/e13-s01.md)
- [ ] E13-S02 — [State persistence per tick](tickets/e13-s02.md)
- [ ] E13-S03 — [Market hours awareness (skip ticks outside hours)](tickets/e13-s03.md)
- [ ] E13-S04 — [CLI: `phantom run --mode paper --interval 300` (scheduler wiring)](tickets/e13-s04.md)

### E17 · Library API Surface (remaining)

- [ ] E17-S13 — [RunnerAPI: paper_trade() + stop() (background thread)](tickets/e17-s13.md)
- [ ] E17-S14 — [ReportAPI: compare_brokers()](tickets/e17-s14.md)
- [ ] E17-S15 — [NoteAPI: edit(), search()](tickets/e17-s15.md)
- [ ] E17-S16 — [Thread safety: write lock on mutating ops](tickets/e17-s16.md)
- [ ] E17-S17 — [Library usage documentation](tickets/e17-s17.md)
- [ ] E17-S18 — [CostEngine as standalone public export](tickets/e17-s18.md)

---

## P3

### E12 · Reporting (P3)

- [ ] E12-S12 — [Terminal equity curve chart (Rich or plotext)](tickets/e12-s12.md)

### E13 · Paper Trade Scheduler (P3)

- [ ] E13-S05 — [systemd service template](tickets/e13-s05.md)

### E14 · Alerts & Notifications

- [ ] E14-S01 — [Define alert event types](tickets/e14-s01.md)
- [ ] E14-S02 — [Alert dispatcher](tickets/e14-s02.md)
- [ ] E14-S03 — [Telegram webhook sender](tickets/e14-s03.md)
- [ ] E14-S04 — [Discord webhook sender](tickets/e14-s04.md)
- [ ] E14-S05 — [CLI config: `phantom config alerts`](tickets/e14-s05.md)

### E15 · Strategy Automation Hooks

- [ ] E15-S01 — [Strategy protocol: on_bar() → list[OrderRequest]](tickets/e15-s01.md)
- [ ] E15-S02 — [Strategy loader (import from user directory)](tickets/e15-s02.md)
- [ ] E15-S03 — [Wire strategy into simulation loop](tickets/e15-s03.md)
- [ ] E15-S04 — [Strategy parameter snapshot on account creation](tickets/e15-s04.md)
- [ ] E15-S05 — [CLI: `phantom run --mode backtest --strategy my_strategy.py`](tickets/e15-s05.md)

### E16 · Web UI

- [ ] E16-S01 — [FastAPI app with CORS, static files, Jinja2](tickets/e16-s01.md)
- [ ] E16-S02 — [Dashboard page: account overview, open positions, recent trades](tickets/e16-s02.md)
- [ ] E16-S03 — [Position detail page: equity chart, cost breakdown, notes](tickets/e16-s03.md)
- [ ] E16-S04 — [Order placement form](tickets/e16-s04.md)
- [ ] E16-S05 — [Broker comparison view](tickets/e16-s05.md)
- [ ] E16-S06 — [HTMX live updates during paper trading](tickets/e16-s06.md)
