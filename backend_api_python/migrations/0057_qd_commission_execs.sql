-- Commission execution records for idempotent accumulation.
-- Each IB execId is recorded at most once; the commission is then
-- added to the parent qd_strategy_trades row via pending_order_id.

CREATE TABLE IF NOT EXISTS qd_commission_execs (
    id          SERIAL PRIMARY KEY,
    trade_id    INTEGER REFERENCES qd_strategy_trades(id) ON DELETE CASCADE,
    exec_id     VARCHAR(80) NOT NULL,
    commission  DECIMAL(20,8) NOT NULL DEFAULT 0,
    currency    VARCHAR(20) DEFAULT '',
    created_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE (exec_id)
);

CREATE INDEX IF NOT EXISTS idx_commission_execs_trade_id
    ON qd_commission_execs(trade_id);
