-- Add margin_call_at field to accounts table for margin call tracking
ALTER TABLE accounts ADD COLUMN margin_call_at TEXT;
