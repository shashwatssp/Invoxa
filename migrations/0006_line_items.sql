-- 0006_line_items.sql
-- Persists the extracted line items (JSON array of
-- {"description": str, "amount": float}) on the invoice row so the
-- detail page can show them.
-- Additive and idempotent; safe to run more than once.

ALTER TABLE invoices ADD COLUMN IF NOT EXISTS line_items jsonb;
