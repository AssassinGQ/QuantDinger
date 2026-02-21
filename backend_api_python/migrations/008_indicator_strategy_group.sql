-- =============================================================================
-- 增量迁移 008: 指标与策略分组 - indicator_group / display_group
-- 可重复执行。PostgreSQL。
-- =============================================================================

-- qd_indicator_codes: 指标自定义分组
ALTER TABLE qd_indicator_codes
  ADD COLUMN IF NOT EXISTS indicator_group VARCHAR(100) DEFAULT 'ungrouped';

-- qd_strategies_trading: 策略自定义分组（与 strategy_group_id 区分，后者为批量创建组）
ALTER TABLE qd_strategies_trading
  ADD COLUMN IF NOT EXISTS display_group VARCHAR(100) DEFAULT 'ungrouped';

CREATE INDEX IF NOT EXISTS idx_indicator_codes_group
  ON qd_indicator_codes(indicator_group);

CREATE INDEX IF NOT EXISTS idx_strategies_display_group
  ON qd_strategies_trading(display_group);
