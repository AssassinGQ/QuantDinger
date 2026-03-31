-- Migration: Add gateway_mode column to pending_orders
-- Purpose: Support multi-gateway (paper/live) order isolation
-- Date: 2026-03-31

ALTER TABLE pending_orders ADD COLUMN IF NOT EXISTS gateway_mode VARCHAR(20) DEFAULT 'paper';

CREATE INDEX IF NOT EXISTS idx_pending_orders_gateway_mode ON pending_orders(gateway_mode);

SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'pending_orders' AND column_name = 'gateway_mode';
