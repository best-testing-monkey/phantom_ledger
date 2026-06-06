# E8: Margin Engine

Margin level monitoring and forced liquidation.

## Stories

- [ ] **E8-S01** `P2` — Implement MarginEngine.check(): compute margin_level = equity / used_margin for an account, return status (ok / margin_call / stop_out)
- [ ] **E8-S02** `P2` — Implement margin call warning: log event, flag account, persist warning timestamp
- [ ] **E8-S03** `P2` — Implement stop-out cascade: when margin_level <= stop_out_level, force-close the position with the largest unrealized loss. Repeat until margin_level recovers or all positions closed. Set close_reason = "margin_call".
- [ ] **E8-S04** `P2` — Integration test: create account with multiple CFD positions, drop price to trigger stop-out, verify correct cascade order and final account state
- [ ] **E8-S05** `P2` — Implement margin level display in `phantom account show` and `phantom position list` for CFD accounts
