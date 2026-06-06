# E15: Strategy Automation Hooks

Allow algorithm accounts to run custom strategy logic on each bar.

## Stories

- [ ] **E15-S01** `P3` — Define Strategy protocol: on_bar(bar, account, engine) -> list[OrderRequest]
- [ ] **E15-S02** `P3` — Implement strategy loader: discover and import strategy classes from a user-specified directory
- [ ] **E15-S03** `P3` — Wire strategy execution into simulation loop: after position updates, call strategy.on_bar(), place returned orders
- [ ] **E15-S04** `P3` — Implement strategy parameter snapshot: when an algorithm account is created, serialize strategy params to algorithm_params
- [ ] **E15-S05** `P3` — CLI: `phantom run --account <name> --mode backtest --strategy my_strategy.py --start 2024-01-01 --end 2025-01-01`
