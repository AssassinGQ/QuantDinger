-- =============================================================================
-- 增量迁移 005: IBKR PnL 数据表
-- 用于存储 IBKR 账户的实时 PnL 数据
-- PostgreSQL
-- =============================================================================

-- IBKR PnL 账户级别实时数据表
CREATE TABLE IF NOT EXISTS qd_ibkr_pnl (
    id SERIAL PRIMARY KEY,
    account VARCHAR(50) NOT NULL UNIQUE,
    daily_pnl DECIMAL(20, 4) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 4) DEFAULT 0,
    realized_pnl DECIMAL(20, 4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- IBKR PnL 逐持仓实时数据表
CREATE TABLE IF NOT EXISTS qd_ibkr_pnl_single (
    id SERIAL PRIMARY KEY,
    account VARCHAR(50) NOT NULL,
    con_id BIGINT NOT NULL,
    symbol VARCHAR(100) NOT NULL DEFAULT '',
    avg_cost DECIMAL(20, 6) DEFAULT 0,
    daily_pnl DECIMAL(20, 4) DEFAULT 0,
    unrealized_pnl DECIMAL(20, 4) DEFAULT 0,
    realized_pnl DECIMAL(20, 4) DEFAULT 0,
    position DECIMAL(20, 8) DEFAULT 0,
    value DECIMAL(20, 4) DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(account, con_id)
);

-- 增量: 如果表已存在但缺少 avg_cost 列, 则添加
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'qd_ibkr_pnl_single' AND column_name = 'avg_cost'
    ) THEN
        ALTER TABLE qd_ibkr_pnl_single ADD COLUMN avg_cost DECIMAL(20, 6) DEFAULT 0;
    END IF;
END $$;

-- 按账户快速查询
CREATE INDEX IF NOT EXISTS idx_ibkr_pnl_account ON qd_ibkr_pnl (account);
CREATE INDEX IF NOT EXISTS idx_ibkr_pnl_single_account ON qd_ibkr_pnl_single (account);
CREATE INDEX IF NOT EXISTS idx_ibkr_pnl_single_conid ON qd_ibkr_pnl_single (con_id);

COMMENT ON TABLE qd_ibkr_pnl IS 'IBKR 账户 PnL 实时数据';
COMMENT ON COLUMN qd_ibkr_pnl.account IS 'IBKR 账户ID';
COMMENT ON COLUMN qd_ibkr_pnl.daily_pnl IS '当日盈亏';
COMMENT ON COLUMN qd_ibkr_pnl.unrealized_pnl IS '未实现盈亏';
COMMENT ON COLUMN qd_ibkr_pnl.realized_pnl IS '已实现盈亏';

COMMENT ON TABLE qd_ibkr_pnl_single IS 'IBKR 逐持仓 PnL 实时数据';
COMMENT ON COLUMN qd_ibkr_pnl_single.account IS 'IBKR 账户ID';
COMMENT ON COLUMN qd_ibkr_pnl_single.con_id IS 'IBKR 合约ID';
COMMENT ON COLUMN qd_ibkr_pnl_single.symbol IS '合约符号';
