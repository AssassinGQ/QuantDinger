-- Drop redundant gateway_mode columns from trades and pending_orders.
-- Isolation between ibkr-live and ibkr-paper is handled by strategy exchange_id.

DROP INDEX IF EXISTS idx_trades_gateway_mode;
DROP INDEX IF EXISTS idx_pending_orders_gateway_mode;

ALTER TABLE qd_strategy_trades DROP COLUMN IF EXISTS gateway_mode;
ALTER TABLE pending_orders DROP COLUMN IF EXISTS gateway_mode;
