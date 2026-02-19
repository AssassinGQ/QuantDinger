-- P1d: regime 切换历史持久化
CREATE TABLE IF NOT EXISTS qd_regime_history (
    id SERIAL PRIMARY KEY,
    from_regime VARCHAR(20),
    to_regime VARCHAR(20) NOT NULL,
    vix DECIMAL(10,4),
    dxy DECIMAL(10,4),
    fear_greed DECIMAL(10,4),
    weights_before JSONB,
    weights_after JSONB,
    strategies_started INTEGER[],
    strategies_stopped INTEGER[],
    strategies_weight_changed INTEGER[],
    trigger_source VARCHAR(20) DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regime_history_created_at
    ON qd_regime_history(created_at DESC);
