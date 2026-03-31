-- Migration: Add gateway_mode column to qd_strategy_trades
-- Purpose: Support multi-gateway (paper/live) trade isolation
-- Date: 2026-03-31

-- Add gateway_mode column with default value 'paper' for existing records
ALTER TABLE qd_strategy_trades ADD COLUMN IF NOT EXISTS gateway_mode VARCHAR(20) DEFAULT 'paper';

-- Add index for faster filtering by gateway_mode
CREATE INDEX IF NOT EXISTS idx_strategy_trades_gateway_mode ON qd_strategy_trades(gateway_mode);

-- Verify the column was added
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'qd_strategy_trades' AND column_name = 'gateway_mode';
