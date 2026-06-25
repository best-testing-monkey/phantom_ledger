# E14: Alerts & Notifications

Notify on significant events during paper trading.

## Stories

- [ ] **E14-S01** `P3` — Define alert event types: order_filled, tp_hit, sl_hit, margin_warning, margin_call, position_expired
- [ ] **E14-S02** `P3` — Implement alert dispatcher: route events to configured channels
- [ ] **E14-S03** `P3` — Implement Telegram webhook sender
- [ ] **E14-S04** `P3` — Implement Discord webhook sender
- [ ] **E14-S05** `P3` — CLI config: `phantom config alerts --telegram-token <tok> --telegram-chat <id>`
