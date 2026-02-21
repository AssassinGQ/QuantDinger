-- Regime 配置改为全局单例，移除 user_id
-- 1. 合并多行：只保留 updated_at 最新且 symbol_strategies 非空的行，若无则保留最新一行
-- 2. 删除 user_id 列

DO $$
DECLARE
  keep_id INT;
BEGIN
  SELECT id INTO keep_id
  FROM qd_regime_config
  ORDER BY (CASE WHEN symbol_strategies != '{}'::jsonb THEN 0 ELSE 1 END), updated_at DESC
  LIMIT 1;

  IF keep_id IS NOT NULL THEN
    DELETE FROM qd_regime_config WHERE id IS DISTINCT FROM keep_id;
  END IF;

  ALTER TABLE qd_regime_config DROP COLUMN IF EXISTS user_id;
  DROP INDEX IF EXISTS idx_regime_config_user_id;
END $$;
