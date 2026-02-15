-- =============================================================================
-- 增量迁移 004: qd_kline_points 支持 5m 回退 — 增加 interval_sec
-- 1m = 60, 5m = 300；5m 可聚合成 1H/4H/1D/1W。可重复执行。
-- PostgreSQL。
-- =============================================================================

-- 新增列，已有行默认为 60（1m）。PostgreSQL 9.6+ 支持 IF NOT EXISTS。
ALTER TABLE qd_kline_points
  ADD COLUMN IF NOT EXISTS interval_sec INTEGER NOT NULL DEFAULT 60;

-- 主键改为 (market, symbol, time_sec, interval_sec)，便于同时存 1m 与 5m
ALTER TABLE qd_kline_points DROP CONSTRAINT qd_kline_points_pkey;
ALTER TABLE qd_kline_points ADD PRIMARY KEY (market, symbol, time_sec, interval_sec);

-- 按品类+粒度查范围
CREATE INDEX IF NOT EXISTS idx_kline_points_interval_lookup
  ON qd_kline_points (market, symbol, interval_sec, time_sec DESC);
