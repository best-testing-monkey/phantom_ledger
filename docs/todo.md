# Phantom Ledger — Web UI Improvement Backlog

Missing features identified by auditing the running web UI against the requirements of a full manual backtesting product. Stories are ordered by dependency (implement earlier stories before later ones where noted).

Tickets live in `docs/tickets/`. Each story is scoped to be implementable by a single agent with limited context — file locations, current state, and implementation hints are included in each ticket.

## QA Status

**QA completed 2026-06-25.** All 14 stories pass. Full findings in [`docs/findings/qa-e16-web-ui.md`](findings/qa-e16-web-ui.md).

One critical bug was found and fixed during QA: HTMX fragment endpoints (`/api/orders-rows`, `/api/positions-rows`, `/api/equity-snapshot`) returned HTTP 500 because `TemplateResponse` was called without the required `request` parameter. Fixed in commit `eb91207`.

**Note:** The running server must be restarted to pick up the new routes. Use `./start_web.sh` or `RELOAD=1 ./start_web.sh` for development.

---

## E16 · Web UI Improvements

### Core interactivity — implement these first

- [x] E16-S07 — [Account switcher on dashboard](tickets/e16-s07.md)
  _Dropdown to switch between accounts; dashboard currently hard-codes the first account._

- [x] E16-S08 — [Open orders panel](tickets/e16-s08.md)
  _Pending/limit orders are invisible after placement. Adds an Open Orders card with cancel buttons. Requires E16-S07 (account context)._

- [x] E16-S09 — [Close position action](tickets/e16-s09.md)
  _No way to close a position from the UI. Adds a Close form on the dashboard row and position detail page._

- [x] E16-S10 — [Simulated clock control panel](tickets/e16-s10.md)
  _No way to set or advance the simulated datetime. Adds a clock widget to the dashboard for set/step-forward/step-back._

### Order management

- [x] E16-S11 — [Order history page](tickets/e16-s11.md)
  _New `/orders` page listing all orders (all statuses) with pagination. Adds "Orders" to the nav._

- [x] E16-S12 — [Modify pending order](tickets/e16-s12.md)
  _Edit limit price, SL, or TP on a pending order. Adds `OrderAPI.modify()` and a form on the order history page. Requires E16-S11._

- [x] E16-S13 — [Partial close position](tickets/e16-s13.md)
  _Close a fraction of a position by specifying quantity. Extends `PositionAPI.close()` and the close form. Requires E16-S09._

### Data visibility

- [x] E16-S14 — [Equity curve chart](tickets/e16-s14.md)
  _Render a Chart.js line chart of account equity on the dashboard. Backend data already exists._

- [x] E16-S15 — [Position cost breakdown panel](tickets/e16-s15.md)
  _Show commission, spread, slippage, overnight, FX costs on the position detail page. Template-only change — all data already on the Position model._

- [x] E16-S16 — [P&L summary panel on dashboard](tickets/e16-s16.md)
  _Show realized P&L, win rate, avg win/loss, profit factor. Calls existing `ReportAPI.account_metrics()`._

### UX fixes

- [x] E16-S17 — [Trade notes from UI](tickets/e16-s17.md)
  _Add and delete notes on the position detail page. Notes are CLI-only today; the detail page only displays them._

- [x] E16-S18 — [Broker comparison fix and account selector](tickets/e16-s18.md)
  _Nav link to `/brokers/compare` immediately errors without `?account=`. Replace with a landing page that shows an account selector._

- [x] E16-S19 — [Order confirmation page](tickets/e16-s19.md)
  _After placing an order the user is silently dropped on the dashboard. Adds a confirmation page showing fill status._

- [x] E16-S20 — [Closed trades pagination on dashboard](tickets/e16-s20.md)
  _Dashboard caps closed trades at 10. Add Previous/Next pagination (25 per page)._

---

## Dependency notes

```
E16-S07 (account switcher)
    └── E16-S08 (open orders)
    └── E16-S09 (close position)
            └── E16-S13 (partial close)
    └── E16-S10 (clock control)

E16-S11 (order history)
    └── E16-S12 (modify order)

E16-S14, S15, S16, S17, S18, S19, S20 — independent, no inter-dependencies
```

Stories without arrows in the graph above can be implemented in any order or in parallel.
