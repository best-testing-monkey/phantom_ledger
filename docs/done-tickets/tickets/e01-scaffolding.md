# E1: Project Scaffolding

Set up the project structure, tooling, and foundation.

## Stories

- [ ] **E1-S01** `MVP` — Initialize uv project with pyproject.toml, src layout, and test directory
- [ ] **E1-S02** `MVP` — Set up SQLite database module with connection pooling and WAL mode
- [ ] **E1-S03** `MVP` — Implement migration runner (read and apply numbered .sql files in order, track applied migrations in a `_migrations` table)
- [ ] **E1-S04** `MVP` — Write initial migration (001_initial.sql) with all MVP tables: accounts, orders, positions, trade_notes, equity_curve
- [ ] **E1-S05** `MVP` — Create api/ module skeleton: Phantom facade class, sub-API stubs, exception hierarchy
- [ ] **E1-S06** `MVP` — Create Typer CLI skeleton with subcommand groups (account, order, position, note, report, data, broker, run, replay) — all commands delegate to api/
- [ ] **E1-S07** `MVP` — Implement config module: load .env, resolve data directory paths, validate required settings
- [ ] **E1-S08** `MVP` — Set up pytest fixtures: in-memory SQLite, Phantom instance with test data dir, sample broker profile, sample price DataFrame
- [ ] **E1-S09** `MVP` — Configure ruff for linting and formatting rules
