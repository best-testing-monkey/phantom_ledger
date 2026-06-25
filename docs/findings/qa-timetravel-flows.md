# QA Findings — Time-Travel Clock Flows

**Date:** 2026-06-25
**Commit:** `586131c` (temporal clock filtering + auto-simulation on forward step)
**Env:** Two accounts in DB — "Test account 1" (EUR) and "Test account 2" (EUR, clean). All steps run against Account 1 only.

---

## Flow: AAPL time-travel with clock rollback and forward

### Setup
- Account 1 (`01KVYPV3S91K1ZEXVMQT8TKVHZ`) — pre-existing closed trades from prior QA sessions (multiple AAPL and NVDA)
- Account 2 (`01KVZ8K1FRJAQXWXXKRWQ4M5GY`) — empty, used only as isolation check

### Step-by-step

| Step | Clock | Action | Expected | Result |
|---|---|---|---|---|
| 1 | Set to `2025-06-25 09:30` | — | Clock updates | ✅ `data/web_clock.json` shows `2025-06-25T09:30:00+00:00` |
| 2 | `2025-06-25 09:30` | Place AAPL market buy, 9.2 shares, Account 1 | Order `created_at = 2025-06-25 09:30` | ✅ Order `01KVZ8S7B380G93XPAK2PAG0HB` in DB with correct timestamp |
| 3 | `2025-06-25 09:30` | Fill order at $200.7635 (actual 2025-06-25 close) | Position created with `entry_datetime = 2025-06-25 09:30` | ✅ Position `01KVZ8VQVMB5KRT2DPAN9CP7V5` created |
| 4 | Advance to `2026-06-24 16:00` | Forward clock set — auto-sim runs, no pending orders → no-op | Clock updates | ✅ No duplicate positions created |
| 5 | `2026-06-24 16:00` | Close position at $293.08 (actual 2026-06-24 close) | `exit_datetime = 2026-06-24 16:00` (simulated) | ✅ Position detail shows entry `2025-06-25 09:30`, exit `2026-06-24 16:00` |
| **A** | **Roll back to `2026-06-17 16:00`** | — | AAPL 9.2 shows in **Open Positions** (exit date is in simulated future) | ✅ "Open Positions" section appears; position `01KVZ8VQVMB5KRT2DPAN9CP7V5` present; no Close button (DB status = closed) |
| **B** | **Roll back to `2025-04-17 09:30`** | — | AAPL not visible (order not placed yet at this date) | ✅ No "Open Positions" section; no pending fill buttons; closed trades shows only NVDA (exited 2021-10-26) |
| **C** | **Roll forward to `2025-10-17 09:30`** | — | AAPL 9.2 reappears as open (entry 2025-06-25 ≤ simulated; exit 2026-06-24 > simulated); no duplicate order | ✅ Open Positions section shows AAPL 9.2; zero pending fill buttons on both accounts |

---

## Isolation: Account 2 unaffected throughout

At every step, Account 2 showed:
- No "Open Positions" section
- No pending orders
- No closed trades

The auto-simulation on forward clock advance correctly skipped Account 2 (no pending orders).

---

## What the temporal filtering does

When `simulated_now` is set, the dashboard (and HTMX position/order fragments) apply this logic:

**Open Positions shown:**
- `status = 'open'` AND `entry_datetime ≤ simulated_now`
- OR `status = 'closed'` AND `entry_datetime ≤ simulated_now` AND `exit_datetime > simulated_now`

**Pending Orders shown:**
- `status = 'pending'` AND `created_at ≤ simulated_now`

**Closed Trades shown:**
- `status = 'closed'` AND `exit_datetime ≤ simulated_now`

When `simulated_now` is not set (wall-clock mode), all DB state is shown as-is.

---

## Known behaviour / not bugs

- **No Close button on "virtually open" positions**: positions that are DB-closed but appear open at simulated time cannot be re-closed via the UI. The DB state is authoritative; the temporal filter is display-only.
- **Multiple historical AAPL rows in Open Positions**: the test DB accumulated many AAPL trades from repeated QA sessions, all sharing entry date `2025-06-25`. This is an artifact of the test environment, not a bug.
- **Auto-simulation runs silently on forward step**: if there are no pending orders for any account, the forward step is a pure clock update with no side effects. The "Run Simulation" button remains available for manual triggering.

---

## Issues found and fixed during this QA cycle

| # | Issue | Status |
|---|---|---|
| 1 | Rolling back clock did not re-open positions (display-only issue) | ✅ Fixed — temporal filtering in dashboard + HTMX fragments |
| 2 | Trade history showed all-time records regardless of simulated clock | ✅ Fixed — closed trades filtered by `exit_datetime ≤ simulated_now` |
| 3 | Rolling clock forward did not trigger simulation | ✅ Fixed — `clock/set` and `clock/step` auto-run backtest for pending orders when moving forward |
| 4 | Clock display showed "UTC" suffix | ✅ Fixed — display now `YYYY-MM-DD HH:MM` |
| 5 | Clock input was `datetime-local` (browser-locale format) | ✅ Fixed — text input with `YYYY-MM-DD HH:MM` format, pre-populated, monospace |
