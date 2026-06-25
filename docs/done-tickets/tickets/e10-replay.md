# E10: Historical Position Replay

Insert a position at any past date and replay it forward to present.

## Stories

- [ ] **E10-S01** `MVP` — Implement ReplayEngine.replay_position(): given a position with historical entry_datetime, load bars from entry to now (or max_close_datetime), step through each bar applying the full position lifecycle (TP/SL/trailing/margin/overnight/dividend)
- [ ] **E10-S02** `MVP` — Handle replay outcome: if exit condition was hit historically, close the position at historical price/time. If no exit by present, leave position open with status "open" and accumulated costs.
- [ ] **E10-S03** `MVP` — CLI: `phantom replay --account <name>` — replay all positions with historical entry dates that haven't been replayed yet
- [ ] **E10-S04** `MVP` — CLI: `phantom replay --position <id>` — replay a single position
- [ ] **E10-S05** `MVP` — Implement replay idempotency: track whether a position has been replayed, prevent double-replay. Store replay_completed_at on position.
- [ ] **E10-S06** `P2` — Implement replay with overnight and dividend hooks (depends on E9-S09, E9-S10)
- [ ] **E10-S07** `P2` — Implement replay with margin simulation (depends on E8-S01)
- [ ] **E10-S08** `P2` — Performance: for bulk replay of many positions on the same ticker, share the price data load across positions
