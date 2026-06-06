# Implementation Standards (Appendix A)

Every story in this project must be implemented against the conventions below.
This file is the authoritative reference — read it before writing any code.

---

## A.1 ID Generation

Use ULIDs for all entity IDs. They sort chronologically, are URL-safe, and encode creation time.

```python
# src/phantom/utils/ids.py
from ulid import ULID

def new_id() -> str:
    """Generate a new ULID as a 26-character string."""
    return str(ULID())
```

- Never use auto-incrementing integers.
- Never use UUID4 (no sort order).
- Every entity gets its ID assigned at creation time in Python, not by the database.

---

## A.2 Datetime Handling

All datetimes are timezone-aware UTC internally.

```python
# src/phantom/utils/datetime.py
from datetime import datetime, timezone

def parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def to_iso(dt: datetime) -> str:
    return dt.isoformat()
```

Rules:
- Store in SQLite as ISO 8601 TEXT with timezone offset (e.g. `2025-06-15T14:30:00+00:00`).
- API methods accept `str | datetime` for datetime parameters.
- Comparison and arithmetic always in UTC. Never compare naive and aware datetimes.
- Display to users in their local context only at the CLI/UI layer.

---

## A.3 Pydantic Models

All domain models use Pydantic v2 `BaseModel`.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from phantom.utils.ids import new_id

class Position(BaseModel):
    id: str = Field(default_factory=new_id)
    account_id: str
    ticker: str
    instrument_type: str  # "stock" or "cfd"
    direction: str        # "long" or "short"
    entry_price: float
    entry_datetime: datetime
    quantity: float
    status: str = "open"

    # nullable fields
    take_profit: float | None = None
    stop_loss: float | None = None
    close_reason: str | None = None
```

Rules:
- Use `Field(default_factory=new_id)` for IDs.
- Nullable fields: always `X | None = None`, never `Optional[X]`.
- Use `Literal` types for constrained string fields (see A.4).
- Model names are singular nouns: `Position`, `Order`, `Account`.
- Default config is mutable (`frozen=False`). Use `frozen=True` only for value objects like `CostBreakdown`.

---

## A.4 Enums and Constants

Use `Literal` types for constrained string fields. Put them in `src/phantom/models/types.py`.

```python
# src/phantom/models/types.py
from typing import Literal

AccountType = Literal["pattern", "manual", "algorithm", "aggregate"]
InstrumentType = Literal["stock", "cfd"]
Direction = Literal["long", "short"]
OrderType = Literal["market", "limit", "stop", "stop_limit", "trailing_stop", "oco"]
OrderStatus = Literal["pending", "triggered", "filled", "expired", "rejected", "cancelled"]
PositionStatus = Literal["open", "closed", "liquidated"]
CloseReason = Literal["tp", "sl", "trailing_sl", "max_time", "margin_call", "manual"]
```

---

## A.5 Exception Patterns

```python
# src/phantom/errors.py

class PhantomError(Exception):
    """Base exception for all Phantom Ledger errors."""

class NotFoundError(PhantomError):
    def __init__(self, entity_type: str, identifier: str):
        self.entity_type = entity_type
        self.identifier = identifier
        super().__init__(f"{entity_type} not found: {identifier}")

class InsufficientFundsError(PhantomError):
    def __init__(self, account_id: str, required: float, available: float):
        self.account_id = account_id
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient funds in {account_id}: "
            f"need {required:.2f}, have {available:.2f}"
        )

class MarginError(PhantomError): ...
class ValidationError(PhantomError): ...
class DataError(PhantomError): ...
class ProfileError(PhantomError): ...
```

Rules:
- Always raise specific subclasses, never bare `PhantomError`.
- `get()` methods raise `NotFoundError` on miss — never return `None`.
- `list()` methods return empty list on no matches.
- CLI layer catches `PhantomError` and renders as user-friendly Rich messages.

---

## A.6 Repository Conventions

```python
# src/phantom/db/repositories/account_repo.py
import sqlite3
from phantom.models.account import Account
from phantom.errors import NotFoundError

class AccountRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, account: Account) -> Account:
        self._conn.execute(
            "INSERT INTO accounts (id, name, ...) VALUES (?, ?, ...)",
            (account.id, account.name, ...),
        )
        self._conn.commit()
        return account

    def get(self, account_id: str) -> Account:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Account", account_id)
        return self._row_to_model(row)

    def get_by_name(self, name: str) -> Account:
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Account", name)
        return self._row_to_model(row)

    def list(self, **filters) -> list[Account]: ...

    def update(self, account: Account) -> Account:
        cursor = self._conn.execute(
            "UPDATE accounts SET name=?, cash=? WHERE id=?",
            (account.name, account.cash, account.id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Account", account.id)
        self._conn.commit()
        return account

    def delete(self, account_id: str) -> None:
        cursor = self._conn.execute(
            "DELETE FROM accounts WHERE id = ?", (account_id,)
        )
        if cursor.rowcount == 0:
            raise NotFoundError("Account", account_id)
        self._conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> Account:
        return Account(**dict(row))
```

Rules:
- Constructor-injected `sqlite3.Connection`. Never create connections inside repos.
- `get()` and `get_by_name()` always raise `NotFoundError` on miss.
- `list()` returns empty list on no matches.
- `create()` returns the model passed in.
- `update()` raises `NotFoundError` if `rowcount == 0`.
- `delete()` raises `NotFoundError` if `rowcount == 0`.
- All write methods call `self._conn.commit()`.
- Use `sqlite3.Row` row factory (set on connection creation).

---

## A.7 API Method Conventions

```python
# src/phantom/api/accounts.py
class AccountAPI:
    def __init__(self, conn: sqlite3.Connection, broker_repo: BrokerRepo):
        self._repo = AccountRepo(conn)
        self._broker_repo = broker_repo

    def create(
        self,
        name: str,
        account_type: str,
        broker: str,
        capital: float,
        currency: str = "EUR",
        pattern_tag: str | None = None,
        algorithm_id: str | None = None,
        ...
    ) -> Account:
        """Create a new account.

        Args:
            name: Unique account name.
            account_type: One of "pattern", "manual", "algorithm", "aggregate".
            broker: Name of a loaded broker profile.
            capital: Starting capital in base currency.
            ...

        Returns:
            The created Account.

        Raises:
            ValidationError: If required type-specific fields are missing.
            NotFoundError: If the broker profile is not loaded.
        """
        profile = self._broker_repo.get_by_name(broker)
        if account_type == "pattern" and not pattern_tag:
            raise ValidationError("pattern_tag is required for pattern accounts")
        account = Account(name=name, ...)
        return self._repo.create(account)
```

Rules:
- Method parameters are primitives: `str`, `float`, `int`, `bool`, `dict`, `list[str]`, `datetime | str`.
- Return types are always Pydantic models or lists of models.
- Docstrings: one-line summary + Args + Returns + Raises (Google style).
- Validation in API layer, not in repo.
- API methods are the transaction boundary for multi-step operations.

---

## A.8 CLI Conventions

```python
import os, typer
from rich.console import Console
from phantom import Phantom
from phantom.errors import PhantomError

console = Console()

def get_phantom() -> Phantom:
    return Phantom(data_dir=os.environ.get("PHANTOM_DATA", "./data"))

@account_app.command("list")
def account_list():
    """List all accounts."""
    try:
        ph = get_phantom()
        accounts = ph.accounts.list()
        table = Table(title="Accounts")
        table.add_column("Name")
        ...
        for a in accounts:
            table.add_row(a.name, ...)
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
```

Rules:
- CLI imports only from `phantom` (public API) and `phantom.errors`.
- Every command wrapped in `try/except PhantomError`.
- Use Rich tables for lists, Rich panels for single-entity display.
- Never use `print()`. Always `console.print()`.
- Exit code 0 on success, 1 on `PhantomError`.
- Destructive commands require `typer.confirm()` unless `--yes` flag passed.
- `get_phantom()` reads `PHANTOM_DATA` env var, defaults to `"./data"`.

---

## A.9 Testing Conventions

### Fixtures (conftest.py)

```python
import pytest, sqlite3
from phantom import Phantom
from phantom.db.database import run_migrations
from phantom.models.broker import (
    BrokerProfile, CommissionModel, SpreadModel, SlippageModel,
    OvernightModel, MarginModel, DividendModel, TradingHoursConfig,
)

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    run_migrations(conn)
    yield conn
    conn.close()

@pytest.fixture
def phantom_instance(tmp_path):
    return Phantom(data_dir=str(tmp_path), in_memory=True)

@pytest.fixture
def degiro_profile():
    return BrokerProfile(
        name="DEGIRO_TEST",
        commission=CommissionModel(model_type="fixed", fixed_fee=1.0),
        spread=SpreadModel(model_type="fixed", fixed_spread_pct=0.0005),
        slippage=SlippageModel(model_type="fixed_pct", fixed_pct=0.0003),
        overnight=OvernightModel(
            long_markup_pct=0.0, short_markup_pct=0.0,
            day_divisor=365, rate_source="manual", manual_rate=0.0,
        ),
        margin=MarginModel(
            default_margin_pct=1.0, margin_call_level=1.0, stop_out_level=0.5,
        ),
        dividend=DividendModel(
            withholding_rates={"US": 0.15, "NL": 0.15},
            cfd_dividend_adjustment=1.0, cfd_short_dividend_charge=1.0,
        ),
        fx_conversion_pct=0.0025, fx_base_currency="EUR",
        min_order_size=1.0, max_leverage=1.0,
        trading_hours=TradingHoursConfig(
            timezone="America/New_York", open="09:30", close="16:00",
            pre_market=False, post_market=False,
        ),
        supported_instruments=["stock", "etf"],
    )

@pytest.fixture
def sample_price_data():
    import pandas as pd, numpy as np
    dates = pd.bdate_range("2025-01-02", periods=20)
    base = 185.0
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(20).cumsum() * 0.5
    closes = base + noise
    return pd.DataFrame({
        "Open": closes - rng.random(20) * 0.5,
        "High": closes + rng.random(20) * 1.0,
        "Low": closes - rng.random(20) * 1.0,
        "Close": closes,
        "Adj Close": closes,
        "Volume": rng.integers(1_000_000, 10_000_000, 20),
    }, index=dates)
```

### Test Structure

```python
class TestFixedCommission:
    def test_flat_fee_applied(self):
        model = CommissionModel(model_type="fixed", fixed_fee=1.0)
        result = model.calculate(quantity=10, price=185.0, monthly_volume=0)
        assert result == 1.0

    def test_flat_fee_independent_of_quantity(self):
        model = CommissionModel(model_type="fixed", fixed_fee=2.50)
        assert model.calculate(quantity=1, price=100.0, monthly_volume=0) == 2.50
        assert model.calculate(quantity=1000, price=100.0, monthly_volume=0) == 2.50
```

Rules:
- Test class names: `TestXxx`. Method names: `test_<behavior>`.
- Use exact equality (`assert result == 1.0`) for deterministic calculations.
- Use `pytest.approx()` only when float accumulation error is expected.
- Every cost model test: one basic case + one edge case + one boundary case.
- Integration tests: use `phantom_instance` fixture, exercise public API only.
- **Never mock the database.** Use in-memory SQLite fixture.
- Mock only external HTTP calls (yfinance, central bank APIs) with `unittest.mock.patch`.
- Test files runnable independently: `pytest tests/unit/test_commission.py`.

---

## A.10 Import Conventions

```python
# Standard library
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Third party
import pandas as pd
from pydantic import BaseModel, Field

# Internal — always absolute imports from package root
from phantom.models.account import Account
from phantom.models.types import AccountType, Direction
from phantom.errors import NotFoundError, ValidationError
from phantom.utils.ids import new_id
from phantom.utils.datetime import parse_datetime, now_utc, to_iso
```

Rules:
- Always absolute imports. Never `from .models import ...` relative imports.
- Groups: stdlib → third-party → internal, separated by blank lines.
- Import specific names: `from phantom.errors import NotFoundError`, not `import phantom.errors`.

---

## A.11 Logging

```python
import logging
logger = logging.getLogger(__name__)

# In methods:
logger.info("Order %s filled at %.2f", order.id, fill_price)
logger.warning("Margin level %.1f%% below call threshold", margin_level * 100)
logger.error("Failed to fetch price data for %s: %s", ticker, exc)
```

Rules:
- Use `%s` formatting (not f-strings) for lazy evaluation.
- DEBUG: per-bar loop detail. INFO: fills/closes/margin calls. WARNING: degraded state. ERROR: non-fatal failures.
- Never log at CRITICAL. Let exceptions propagate.

---

## A.12 SQL Conventions

- Parameterized queries only (`?` placeholders). Never f-string or `.format()` SQL.
- Table names: `snake_case` plural (`accounts`, `orders`, `positions`, `trade_notes`).
- Column names: `snake_case` matching Pydantic field names exactly.
- JSON blobs: serialize with `json.dumps()`, deserialize with `json.loads()` in `_row_to_model()`.
- `PRAGMA foreign_keys = ON` on every connection.
- `PRAGMA journal_mode = WAL` on every connection.

---

## A.13 Reference Implementation

The broker profile loader is the canonical vertical slice. Every other module follows this layering: model → file loader / repo → API method → CLI command → tests.

```python
# src/phantom/profiles/loader.py
import json
from pathlib import Path
from phantom.models.broker import BrokerProfile
from phantom.errors import ProfileError

def load_profile(path: str | Path) -> BrokerProfile:
    path = Path(path)
    if not path.exists():
        raise ProfileError(f"Profile file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProfileError(f"Invalid JSON in {path}: {e}") from e
    profile_section = raw.get("profile", {})
    flat = {
        **profile_section,
        "commission": raw.get("commission", {}),
        "spread": raw.get("spread", {}),
        "slippage": raw.get("slippage", {}),
        "overnight": raw.get("overnight", {}),
        "margin": raw.get("margin", {}),
        "dividend": raw.get("dividend", {}),
        "trading_hours": raw.get("trading_hours", {}),
    }
    try:
        return BrokerProfile(**flat)
    except Exception as e:
        raise ProfileError(f"Validation failed for {path}: {e}") from e
```

```python
# src/phantom/db/repositories/broker_repo.py
class BrokerRepo:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, profile: BrokerProfile) -> BrokerProfile:
        self._conn.execute(
            "INSERT INTO broker_profiles (id, name, config_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (new_id(), profile.name, profile.model_dump_json(),
             to_iso(now_utc()), to_iso(now_utc())),
        )
        self._conn.commit()
        return profile

    def get_by_name(self, name: str) -> BrokerProfile:
        row = self._conn.execute(
            "SELECT config_json FROM broker_profiles WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise NotFoundError("BrokerProfile", name)
        return BrokerProfile.model_validate_json(row["config_json"])

    def list(self) -> list[BrokerProfile]:
        rows = self._conn.execute(
            "SELECT config_json FROM broker_profiles ORDER BY name"
        ).fetchall()
        return [BrokerProfile.model_validate_json(r["config_json"]) for r in rows]

    def delete(self, name: str) -> None:
        cursor = self._conn.execute(
            "DELETE FROM broker_profiles WHERE name = ?", (name,)
        )
        if cursor.rowcount == 0:
            raise NotFoundError("BrokerProfile", name)
        self._conn.commit()
```

```python
# src/phantom/api/brokers.py
class BrokerAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._repo = BrokerRepo(conn)

    def load(self, path: str) -> BrokerProfile:
        profile = load_profile(path)
        return self._repo.create(profile)

    def list(self) -> list[BrokerProfile]:
        return self._repo.list()

    def get(self, name: str) -> BrokerProfile:
        return self._repo.get_by_name(name)

    def validate(self, path: str) -> BrokerProfile:
        return load_profile(path)
```

```python
# CLI example
@broker_app.command("list")
def broker_list():
    try:
        ph = get_phantom()
        profiles = ph.brokers.list()
        table = Table(title="Broker Profiles")
        table.add_column("Name")
        table.add_column("Commission Type")
        for p in profiles:
            table.add_row(p.name, p.commission.model_type)
        console.print(table)
    except PhantomError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)
```

```python
# Test example
class TestBrokerRepo:
    def test_create_and_get(self, db_conn, degiro_profile):
        from phantom.db.repositories.broker_repo import BrokerRepo
        repo = BrokerRepo(db_conn)
        repo.create(degiro_profile)
        result = repo.get_by_name("DEGIRO_TEST")
        assert result.name == "DEGIRO_TEST"
        assert result.commission.fixed_fee == 1.0

    def test_get_nonexistent_raises(self, db_conn):
        from phantom.db.repositories.broker_repo import BrokerRepo
        from phantom.errors import NotFoundError
        repo = BrokerRepo(db_conn)
        with pytest.raises(NotFoundError):
            repo.get_by_name("NOPE")
```
