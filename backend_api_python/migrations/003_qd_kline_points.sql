-- =============================================================================
-- 增量迁移 003: K线数据点表 (qd_kline_points) — 单粒度 1m 存储
-- 只存 1 分钟数据点，5m/15m/1D 等由读时聚合得到，便于复用与增量更新。
-- 可重复执行。
-- =============================================================================

CREATE TABLE IF NOT EXISTS qd_kline_points (
    market VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    time_sec BIGINT NOT NULL,
    open_price DECIMAL(20,8) NOT NULL,
    high_price DECIMAL(20,8) NOT NULL,
    low_price DECIMAL(20,8) NOT NULL,
    close_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (market, symbol, time_sec)
);

CREATE INDEX IF NOT EXISTS idx_kline_points_lookup ON qd_kline_points(market, symbol, time_sec DESC);
