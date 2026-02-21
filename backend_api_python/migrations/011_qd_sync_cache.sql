-- =============================================================================
-- 011: 同步缓存表 (qd_sync_cache) - 存储新闻、基本盘等定时同步结果
-- 供 API 读取，避免每次请求都拉网络
-- 可重复执行。
-- =============================================================================

CREATE TABLE IF NOT EXISTS qd_sync_cache (
    cache_key VARCHAR(64) PRIMARY KEY,
    value_json TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_cache_updated ON qd_sync_cache(updated_at DESC);
