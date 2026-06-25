# QA Findings — Manual Backtesting Flows

**Date:** 2026-06-25  
**Flows tested:**
1. NVDA — place 1 year ago, close yesterday
2. AAPL — place 5 years ago with 3% TP / 1% SL, advance clock to today

---

## What worked (web UI)

- Equity curve chart rendered with 1374 real AAPL price bars across 5 years — beautiful
- Performance Summary updated: Realized P&L 14.49, 1 trade, 100% Win Rate, ∞ Profit Factor displayed correctly
- Closed trade row in dashboard: symbol, side, qty, entry price, exit price, P&L, close reason, date — all correct
- Position detail page: entry/exit price, duration ("0 days"), realized P&L (14.49), close reason ("sl") all shown
- Cost breakdown on position detail: spread 0.39, slippage 0.26, FX conversion 1.30, total 1.95 — correct
- Add Note form on the closed position — functional
- Clock step buttons (±1d, ±7d) work correctly after setting a date

---

## Flow 1 — NVDA historical trade

### Missing: simulated clock does not stamp orders

**What happened:** Clock was set to 2025-06-25 09:30 before placing the NVDA order. The order was confirmed and appeared in Open Orders. Its `created_at` was **2026-06-25 08:48** (today's wall clock), not 2025-06-25.

**Root cause:** `OrderAPI.place()` calls `now_utc()` internally, not the simulated clock. The clock in `src/phantom/web/clock.py` stores a value but nothing reads it at order placement time.

**Impact:** It is impossible to place a historically-dated order from the web UI. The `--at` CLI flag is the only way.

### Missing: no mechanism to fill a market order from the web UI

After placing the NVDA market order, it sat **pending** indefinitely. Moving the clock from 2025-06-25 to 2026-06-24 (1 year forward) had zero effect — the order never filled, no position was created, cash was unchanged.

There is no "Fill Order at $X" button, no "Run Next Bar" button, and no automatic engine loop triggered by the clock widget.

**Full web UI flow was not completable.** The NVDA trade required:
1. CLI: `phantom order place --ticker NVDA ... --at "2025-06-25T09:30"`
2. CLI: `ph.runner.backtest(account_id=..., tickers=['NVDA'], start=..., end=...)`

---

## Flow 2 — AAPL with TP/SL

### TP/SL fields accepted but not displayed in Open Orders

The Place Order form has Stop Loss and Take Profit fields ✅. Values were submitted (SL=131.67, TP=136.99). However:
- The Open Orders dashboard panel has no TP or SL columns
- There is no way to verify the TP/SL values were stored without going to the Orders history page

### Clock advance does not evaluate TP/SL

Moving the simulated clock from 2021-06-25 to 2026-06-25 (5 years) showed no change: order still pending, no position, cash unchanged. The clock widget is display-only — it does not invoke the simulation engine.

### TP/SL evaluation result (via CLI backtest engine)

After running the backtest via `ph.runner.backtest()`:

| Field | Value |
|---|---|
| Entry | $130.0904 on 2021-06-25 |
| SL set | $131.67 |
| TP set | $136.99 |
| Exit | $131.67 on 2021-06-25 |
| Duration | 0 days |
| Close reason | `sl` |
| Realized P&L | +$14.49 |

**Why SL triggered immediately:** The SL ($131.67) was set ABOVE the actual entry price ($130.09). This happened because the TP/SL were calibrated assuming AAPL entry at $133 (a reasonable mid-2021 assumption), but the actual open on 2021-06-25 was $130.09.

**Engine rule for long positions:** `sl_hit = (bar.low <= stop_loss)`. On the entry bar, low=$129.46 ≤ SL=$131.67 → SL triggered immediately. Exit is recorded at the SL price ($131.67), which is above entry, so P&L is positive (+$14.49) despite a "stop loss" trigger. The bar's actual high was only $130.51, so $131.67 was never genuinely traded that day — the engine exits at the SL price regardless.

**Root cause of wrong calibration:** The web UI has no way to show the current/historical market price for a symbol before placing an order. The user has no reference point to set TP/SL correctly relative to the actual fill price.

### Close Reason displayed as raw code

Position detail page shows Close Reason: **`sl`** — the internal enum value rather than a human label like "Stop Loss". Same would apply to `tp`, `manual`, `margin_call`.

---

## Summary of missing web UI features for manual backtesting

| # | Missing Feature | Workaround |
|---|---|---|
| 1 | Orders inherit simulated clock datetime as `created_at` | CLI `--at` flag |
| 2 | "Fill Order at $X" button for pending market orders | CLI `phantom replay` or backtest |
| 3 | "Run bar / advance engine" when clock steps forward | CLI `ph.runner.backtest()` |
| 4 | TP/SL values shown in Open Orders dashboard table | Orders history page (partially) |
| 5 | Current/historical market price preview before order placement | External data lookup |
| 6 | Close Reason rendered as human label ("Stop Loss") not code ("sl") | None |

Features 1–3 are the core gap: the simulated clock is purely cosmetic. To actually run the engine, the CLI or library API is required. This is by design for the current implementation but represents the biggest usability gap for a manual backtesting workflow.
