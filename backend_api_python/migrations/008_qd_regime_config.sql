-- Regime 配置表：存储 symbol_strategies、regime_to_weights 等，regime_switch 运行时仅从 DB 读取
CREATE TABLE IF NOT EXISTS qd_regime_config (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
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
