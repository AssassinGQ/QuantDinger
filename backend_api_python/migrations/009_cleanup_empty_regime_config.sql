-- 删除 symbol_strategies 为空的无用配置记录
DELETE FROM qd_regime_config WHERE symbol_strategies = '{}'::jsonb;
