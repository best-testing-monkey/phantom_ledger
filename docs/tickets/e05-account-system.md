# E5: Account System

Create and manage accounts of all four types.

## Stories

- [ ] **E5-S01** `MVP` — Implement Account model (Pydantic) with account_type enum (pattern, manual, algorithm, aggregate)
- [ ] **E5-S02** `MVP` — Implement account_repo: create, read, update, list, delete accounts in SQLite
- [ ] **E5-S03** `MVP` — CLI: `phantom account create` with --type, --broker, --capital, --currency, and type-specific flags (--pattern, --algorithm-id, --algorithm-version, --children)
- [ ] **E5-S04** `MVP` — CLI: `phantom account list` (tabular display with Rich) and `phantom account show <name>`
- [ ] **E5-S05** `P2` — Implement aggregate account computation: iterate child accounts, sum equity curves, compute combined metrics (no own positions)
- [ ] **E5-S06** `P2` — Implement account-level margin tracking: used_margin, free_margin, margin_level as computed properties from open CFD positions
- [ ] **E5-S07** `P2` — Validation: reject short/CFD orders on accounts whose broker profile does not list "cfd" in supported_instruments
- [ ] **E5-S08** `P2` — CLI: `phantom account delete <name>` with confirmation prompt and cascade warning
