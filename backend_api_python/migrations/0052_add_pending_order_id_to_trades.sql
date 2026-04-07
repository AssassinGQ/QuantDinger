-- Add pending_order_id to qd_strategy_trades for fill idempotency
ALTER TABLE qd_strategy_trades
    ADD COLUMN IF NOT EXISTS pending_order_id INTEGER DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_trades_pending_order_id
    ON qd_strategy_trades (pending_order_id)
    WHERE pending_order_id IS NOT NULL;
