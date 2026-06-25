# E12: Reporting & Analytics

Compute and display performance metrics, equity curves, and cost breakdowns.

## Stories

- [ ] **E12-S01** `MVP` — Implement metrics calculator: total return, CAGR, max drawdown, max drawdown duration from equity curve
- [ ] **E12-S02** `MVP` — Implement trade-level metrics: win rate, average win, average loss, profit factor, expectancy from closed positions
- [ ] **E12-S03** `MVP` — Implement cost breakdown aggregation: sum commissions, spread, slippage, overnight, FX, dividends across all closed positions in an account
- [ ] **E12-S04** `MVP` — CLI: `phantom report --account <name>` — display metrics table and cost breakdown via Rich
- [ ] **E12-S05** `P2` — Implement Sharpe ratio and Sortino ratio from daily equity returns
- [ ] **E12-S06** `P2` — Implement per-pattern-tag filtering: report metrics for a subset of positions matching a pattern
- [ ] **E12-S07** `P2` — Implement per-algorithm-version filtering
- [ ] **E12-S08** `P2` — Implement aggregate account reporting: combine equity curves from child accounts, compute portfolio-level metrics
- [ ] **E12-S09** `P2` — Implement cost comparison: take a set of closed trades, replay their costs through multiple BrokerProfiles, display side-by-side
- [ ] **E12-S10** `P2` — CLI: `phantom report --compare-brokers degiro,ibkr,xtb --account <name>`
- [ ] **E12-S11** `P2` — Export equity curve to CSV for external charting
- [ ] **E12-S12** `P3` — Implement terminal-based equity curve chart (Rich or plotext)
