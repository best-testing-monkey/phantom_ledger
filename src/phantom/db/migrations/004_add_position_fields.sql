-- Add trailing stop tracking and overnight/dividend tracking fields to positions
ALTER TABLE positions ADD COLUMN trailing_stop_distance REAL;
ALTER TABLE positions ADD COLUMN peak_price REAL;
ALTER TABLE positions ADD COLUMN overnight_accrued REAL NOT NULL DEFAULT 0;
ALTER TABLE positions ADD COLUMN last_bar_date TEXT;
ALTER TABLE positions ADD COLUMN country_code TEXT;

-- Update overnight_log and dividend_log tables to match new schema
DROP TABLE IF EXISTS overnight_log;
CREATE TABLE overnight_log (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    date            TEXT NOT NULL,
    rate            REAL NOT NULL,
    charge_amount   REAL NOT NULL,
    created_at      TEXT NOT NULL
);

DROP TABLE IF EXISTS dividend_log;
CREATE TABLE dividend_log (
    id              TEXT PRIMARY KEY,
    position_id     TEXT NOT NULL REFERENCES positions(id),
    account_id      TEXT NOT NULL REFERENCES accounts(id),
    ex_date         TEXT NOT NULL,
    dividend_per_share REAL NOT NULL,
    adjustment_amount REAL NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX idx_overnight_log_position ON overnight_log(position_id);
CREATE INDEX idx_overnight_log_account ON overnight_log(account_id);
CREATE INDEX idx_dividend_log_position ON dividend_log(position_id);
CREATE INDEX idx_dividend_log_account ON dividend_log(account_id);

-- Update close_reason constraint to include trailing_stop
-- SQLite doesn't support altering CHECK constraints, so we rely on application validation
