# E9: Simulation Engine

The unified backtest and paper-trade execution loop.

## Stories

- [ ] **E9-S01** `MVP` — Implement BacktestClock: step through a DatetimeIndex of bar timestamps, expose now() and advance()
- [ ] **E9-S02** `MVP` — Implement SimulationEngine.run_backtest(): iterate bars via clock, on each bar call OrderManager.evaluate() then PositionManager.update() for all open positions, record equity point
- [ ] **E9-S03** `MVP` — Implement equity curve recording: after each bar, compute account equity (cash + sum of position market values), persist EquityPoint
- [ ] **E9-S04** `MVP` — Integration test: place a market order with TP/SL in the past, run backtest, verify position opens, hits TP or SL, closes with correct P&L and costs
- [ ] **E9-S05** `P2` — Implement LiveClock: return wall-clock time, advance() sleeps until next tick interval
- [ ] **E9-S06** `P2` — Implement SimulationEngine.run_paper(): same loop as backtest but uses LiveClock + LiveProvider, persists state after each tick
- [ ] **E9-S07** `P2` — CLI: `phantom run --account <name> --mode paper --interval 300`
- [ ] **E9-S08** `P2` — Implement graceful shutdown: catch SIGINT/SIGTERM, persist current state, log clean exit
- [ ] **E9-S09** `P2` — Implement overnight cost accrual hook in simulation loop: detect day boundary crossings, call CostEngine.overnight_cost() for each open CFD position
- [ ] **E9-S10** `P2` — Implement dividend hook in simulation loop: check dividend calendar on each bar, apply adjustments via CostEngine
- [ ] **E9-S11** `P2` — Implement margin check hook in simulation loop: after position updates, call MarginEngine.check() for accounts with CFD positions
