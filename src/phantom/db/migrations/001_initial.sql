CREATE TABLE broker_profiles (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    config_json     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE accounts (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    account_type    TEXT NOT NULL CHECK(account_type IN
                        ('pattern', 'manual', 'algorithm', 'aggregate')),
    broker_profile_id TEXT REFERENCES broker_profiles(id),
    base_currency   TEXT NOT NULL DEFAULT 'EUR',
    initial_capital REAL NOT NULL,
    cash            REAL NOT NULL,
    created_at      TEXT NOT NULL,
    pattern_tag         TEXT,
    algorithm_id        TEXT,
    algorithm_version   TEXT,
    algorithm_params    TEXT,
    child_account_ids   TEXT
);

CREATE TABLE orders (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    ticker          TEXT NOT NULL,
    instrument_type TEXT NOT NULL CHECK(instrument_type IN ('stock', 'cfd')),
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    order_type      TEXT NOT NULL CHECK(order_type IN
                        ('market', 'limit', 'stop', 'stop_limit',
                         'trailing_stop', 'oco')),
    quantity        REAL NOT NULL,
    limit_price     REAL,
    stop_price      REAL,
    trailing_amount REAL,
    trailing_pct    REAL,
    take_profit     REAL,
    stop_loss       REAL,
    status          TEXT NOT NULL CHECK(status IN
                        ('pending', 'triggered', 'filled', 'expired',
                         'rejected', 'cancelled')),
    created_at      TEXT NOT NULL,
    triggered_at    TEXT,
    filled_at       TEXT,
    fill_price      REAL,
    good_til        TEXT,
    max_close_datetime TEXT,
    rejection_reason TEXT,
    position_id     TEXT REFERENCES positions(id)
);

CREATE TABLE positions (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    ticker          TEXT NOT NULL,
    instrument_type TEXT NOT NULL CHECK(instrument_type IN ('stock', 'cfd')),
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    entry_order_id  TEXT NOT NULL REFERENCES orders(id),
    entry_price     REAL NOT NULL,
    entry_datetime  TEXT NOT NULL,
    quantity        REAL NOT NULL,
    notional        REAL NOT NULL,
    take_profit     REAL,
    stop_loss       REAL,
    trailing_stop_amount REAL,
    trailing_stop_pct    REAL,
    trailing_stop_peak   REAL,
    max_close_datetime   TEXT,
    commission_entry REAL NOT NULL DEFAULT 0,
    commission_exit  REAL NOT NULL DEFAULT 0,
    spread_cost     REAL NOT NULL DEFAULT 0,
    slippage_cost   REAL NOT NULL DEFAULT 0,
    overnight_costs REAL NOT NULL DEFAULT 0,
    dividend_adjustments REAL NOT NULL DEFAULT 0,
    fx_conversion_cost   REAL NOT NULL DEFAULT 0,
    margin_required REAL NOT NULL DEFAULT 0,
    leverage        REAL NOT NULL DEFAULT 1.0,
    exit_price      REAL,
    exit_datetime   TEXT,
    realized_pnl    REAL,
    status          TEXT NOT NULL CHECK(status IN
                        ('open', 'closed', 'liquidated')),
    close_reason    TEXT CHECK(close_reason IN
                        ('tp', 'sl', 'trailing_sl', 'max_time',
                         'margin_call', 'manual', NULL)),
    pattern_tag     TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE trade_notes (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    title           TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    content_size    INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE equity_curve (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    timestamp       TEXT NOT NULL,
    equity          REAL NOT NULL,
    cash            REAL NOT NULL,
    unrealized_pnl  REAL NOT NULL,
    used_margin     REAL NOT NULL DEFAULT 0,
    drawdown_pct    REAL NOT NULL DEFAULT 0
);

CREATE TABLE overnight_log (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    date            TEXT NOT NULL,
    reference_rate  REAL NOT NULL,
    charge          REAL NOT NULL
);

CREATE TABLE dividend_log (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    ex_date         TEXT NOT NULL,
    gross_amount    REAL NOT NULL,
    net_amount      REAL NOT NULL,
    withholding     REAL NOT NULL
);

CREATE INDEX idx_orders_account ON orders(account_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_positions_account ON positions(account_id);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_equity_account_ts ON equity_curve(account_id, timestamp);
CREATE INDEX idx_notes_position ON trade_notes(position_id);
