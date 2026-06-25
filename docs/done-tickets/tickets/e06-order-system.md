# E6: Order System

Place, track, and execute orders through their lifecycle.

## Stories

- [ ] **E6-S01** `MVP` — Implement Order model with all fields: type, direction, prices, status, timestamps, good_til, max_close_datetime
- [ ] **E6-S02** `MVP` — Implement order_repo: create, read, update status, list by account/status
- [ ] **E6-S03** `MVP` — Implement OrderManager.place(): validate order against account state (sufficient cash/margin), persist as "pending"
- [ ] **E6-S04** `MVP` — Implement OrderManager.evaluate(): given a price bar, check if pending orders should trigger/fill. Market orders fill immediately. Limit orders fill when price reaches limit.
- [ ] **E6-S05** `MVP` — On fill: compute entry costs via CostEngine, deduct from account cash, create Position record, link order to position
- [ ] **E6-S06** `MVP` — Implement order expiry: on each bar, expire orders past good_til datetime
- [ ] **E6-S07** `MVP` — CLI: `phantom order place` with all flags (--at for historical timestamp)
- [ ] **E6-S08** `MVP` — CLI: `phantom order list`, `phantom order cancel <id>`
- [ ] **E6-S09** `P2` — Implement Stop order: trigger market order when price crosses stop_price
- [ ] **E6-S10** `P2` — Implement Stop-Limit order: trigger limit order when price crosses stop_price
- [ ] **E6-S11** `P2` — Implement Trailing Stop order: track peak price, trigger when price retraces by trailing_amount or trailing_pct
- [ ] **E6-S12** `P2` — Implement OCO (One-Cancels-Other): link TP and SL orders, cancel sibling on fill
- [ ] **E6-S13** `P2` — Implement margin validation on order placement: reject if insufficient free margin for CFD orders
- [ ] **E6-S14** `P2` — Implement order rejection reasons: insufficient funds, margin, outside trading hours, unsupported instrument
