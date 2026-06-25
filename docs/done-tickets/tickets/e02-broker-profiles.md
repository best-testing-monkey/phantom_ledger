# E2: Broker Profile System

Define, load, validate, and persist broker cost configurations.

## Stories

- [ ] **E2-S01** `MVP` — Define BrokerProfile Pydantic model with all sub-models (CommissionModel, SpreadModel, SlippageModel, OvernightModel, MarginModel, DividendModel, TradingHoursConfig)
- [ ] **E2-S02** `MVP` — Implement JSON loader: read a .json file, validate against BrokerProfile schema, return typed object
- [ ] **E2-S03** `MVP` — Write DEGIRO broker profile JSON (stock-only, fixed commission, dynamic spread, NL dividend withholding)
- [ ] **E2-S04** `MVP` — Implement broker_repo: save/load BrokerProfile JSON to broker_profiles table
- [ ] **E2-S05** `MVP` — CLI: `phantom broker list` and `phantom broker show <name>`
- [ ] **E2-S06** `P2` — Write IBKR broker profile JSON (tiered commission, per-share model, CFD overnight)
- [ ] **E2-S07** `P2` — Write XTB broker profile JSON (zero-commission stocks, CFD spread/overnight)
- [ ] **E2-S08** `P2` — CLI: `phantom broker validate <file>` — parse and report errors without saving
