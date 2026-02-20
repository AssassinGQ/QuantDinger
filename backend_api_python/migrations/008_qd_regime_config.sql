-- Regime 配置持久化（方案 B：独立配置页，仅 DB，不读 YAML）
CREATE TABLE IF NOT EXISTS qd_regime_config (
    id SERIAL PRIMARY KEY,
    user_id INTEGER DEFAULT NULL,
    symbol_strategies JSONB DEFAULT '{}',
    regime_to_weights JSONB DEFAULT '{}',
    regime_rules JSONB DEFAULT '{}',
    regime_to_style JSONB DEFAULT '{}',
    multi_strategy JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regime_config_user_id ON qd_regime_config(user_id);
CREATE INDEX IF NOT EXISTS idx_regime_config_updated_at ON qd_regime_config(updated_at DESC);
