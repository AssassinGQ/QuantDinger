-- TRADE-02: cumulative snapshot for partial fills (IBKR PartiallyFilled)
ALTER TABLE pending_orders
    ADD COLUMN IF NOT EXISTS remaining DECIMAL(20, 8) DEFAULT 0;
