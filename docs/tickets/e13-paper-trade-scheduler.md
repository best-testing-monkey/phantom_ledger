# E13: Paper Trade Scheduler

Automated paper trading on a timer.

## Stories

- [ ] **E13-S01** `P2` — Implement APScheduler integration: configure interval trigger, run simulation tick on schedule
- [ ] **E13-S02** `P2` — Implement state persistence per tick: after each tick, commit all position/order/equity changes to DB
- [ ] **E13-S03** `P2` — Implement market hours awareness: skip ticks outside trading hours (per broker profile TradingHoursConfig)
- [ ] **E13-S04** `P2` — CLI: `phantom run --account <name> --mode paper --interval 300` — start scheduler, run until SIGINT
- [ ] **E13-S05** `P3` — Implement systemd service template for long-running paper trade
