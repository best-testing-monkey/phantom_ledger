# E17: Library API Surface

The public Python API that both the CLI and external consumers use. The Phantom facade, sub-API classes, exception hierarchy, and re-exports from `__init__.py`.

## Stories

- [ ] **E17-S01** `MVP` — Implement PhantomError exception hierarchy: PhantomError, NotFoundError, InsufficientFundsError, MarginError, ValidationError, DataError, ProfileError
- [ ] **E17-S02** `MVP` — Implement Phantom facade class: accept data_dir and in_memory flag, initialize DB connection, expose sub-API attributes
- [ ] **E17-S03** `MVP` — Implement AccountAPI: create(), list(), get(), delete() — delegates to account_repo and validates inputs
- [ ] **E17-S04** `MVP` — Implement BrokerAPI: load(), list(), get(), validate() — delegates to profile loader and broker_repo
- [ ] **E17-S05** `MVP` — Implement OrderAPI: place(), list(), cancel() — delegates to OrderManager, validates account exists, returns full Order with computed costs
- [ ] **E17-S06** `MVP` — Implement PositionAPI: list(), get(), close(), modify() — delegates to PositionManager
- [ ] **E17-S07** `MVP` — Implement NoteAPI: add(), add_from_file(), list(), get() — delegates to NoteManager
- [ ] **E17-S08** `MVP` — Implement RunnerAPI: replay(), replay_position(), backtest() — delegates to SimulationEngine and ReplayEngine
- [ ] **E17-S09** `MVP` — Implement DataAPI: fetch_prices(), fetch_rates() — delegates to data providers
- [ ] **E17-S10** `MVP` — Implement ReportAPI: account_metrics(), cost_breakdown() — delegates to metrics calculator
- [ ] **E17-S11** `MVP` — Set up `phantom/__init__.py` with public re-exports: Phantom, Account, Order, Position, BrokerProfile, CostEngine, PhantomError and subclasses
- [ ] **E17-S12** `MVP` — Refactor CLI module: strip all business logic, make every command a thin wrapper that calls the corresponding API method and formats output with Rich
- [ ] **E17-S13** `P2` — Implement RunnerAPI: paper_trade() with background thread and stop() method
- [ ] **E17-S14** `P2` — Implement ReportAPI: compare_brokers() — run trades through multiple profiles
- [ ] **E17-S15** `P2` — Implement NoteAPI: edit(), search()
- [ ] **E17-S16** `P2` — Implement thread safety: write lock on mutating operations, concurrent reads safe
- [ ] **E17-S17** `P2` — Write library usage documentation with examples (README and/or docs/)
- [ ] **E17-S18** `P2` — Implement CostEngine as a standalone public export: usable without a full Phantom instance for quick cost calculations
