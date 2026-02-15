-- =============================================================================
-- 增量迁移 002: K线历史缓存表 (qd_kline_cache)
-- 用于「先库后网」历史K线缓存与数据补全。
-- 可重复执行（CREATE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS）。
-- =============================================================================

-- 历史K线缓存：主键 (market, symbol, timeframe, time_sec)，冲突时 upsert
CREATE TABLE IF NOT EXISTS qd_kline_cache (
    market VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    time_sec BIGINT NOT NULL,
    open_price DECIMAL(20,8) NOT NULL,
    high_price DECIMAL(20,8) NOT NULL,
    low_price DECIMAL(20,8) NOT NULL,
    close_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (market, symbol, timeframe, time_sec)
);

CREATE INDEX IF NOT EXISTS idx_kline_cache_lookup ON qd_kline_cache(market, symbol, timeframe, time_sec DESC);
