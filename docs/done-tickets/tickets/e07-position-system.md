# E7: Position System

Manage position lifecycle from open through exit.

## Stories

- [ ] **E7-S01** `MVP` — Implement Position model with all fields: entry, exit conditions, cost accumulators, status, close_reason
- [ ] **E7-S02** `MVP` — Implement position_repo: create, read, update, list by account/status/ticker
- [ ] **E7-S03** `MVP` — Implement PositionManager.update(): given a price bar, update unrealized P&L, check TP/SL
- [ ] **E7-S04** `MVP` — Implement TP/SL exit logic: detect when bar high/low crosses TP or SL, close position at trigger price, compute exit costs, record close_reason
- [ ] **E7-S05** `MVP` — Implement TP/SL ambiguity handling: when a single bar crosses both, configurable behavior (conservative = SL first, optimistic = TP first, proximity = closest to open)
- [ ] **E7-S06** `MVP` — Implement max_close_datetime: auto-close position when clock reaches deadline
- [ ] **E7-S07** `MVP` — Implement manual close: CLI `phantom position close <id> --reason manual`, compute exit costs at current price
- [ ] **E7-S08** `MVP` — Implement position modify: CLI `phantom position modify <id> --tp X --sl Y`
- [ ] **E7-S09** `MVP` — CLI: `phantom position list` and `phantom position show <id>` (display costs breakdown, unrealized P&L, holding duration)
- [ ] **E7-S10** `P2` — Implement trailing stop tracking: update peak on each bar, trigger when retracement exceeds threshold
- [ ] **E7-S11** `P2` — Implement overnight cost accrual: for each trading day boundary crossed, calculate and accumulate overnight charge using OvernightModel + reference rate
- [ ] **E7-S12** `P2` — Implement overnight_log: persist each daily charge to overnight_log table for auditability
- [ ] **E7-S13** `P2` — Implement dividend processing: on ex-date, apply DividendModel adjustment to position (credit for long stock, CFD adjustment, charge for short CFD)
- [ ] **E7-S14** `P2` — Implement dividend_log: persist each dividend event
- [ ] **E7-S15** `P2` — Implement margin tracking per position: compute margin_required based on MarginModel + notional, update account used_margin
- [ ] **E7-S16** `P2` — Implement stock vs CFD position behavior: stocks have no overnight cost and no leverage; CFDs carry overnight, margin, and leverage. Controlled by instrument_type on the position.
