-- UNIV-01 / UNIV-03: NDX EIV baseline + IC raw payload preservation

CREATE TABLE IF NOT EXISTS qd_nq100_index_eiv (
    trade_date DATE PRIMARY KEY,
    index_symbol VARCHAR(32) NOT NULL,
    eod_index_value NUMERIC(20,6) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'NDX_EIV.csv',
    raw_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qd_nq100_index_eiv_symbol_date
    ON qd_nq100_index_eiv(index_symbol, trade_date DESC);

CREATE TABLE IF NOT EXISTS qd_nq100_ic_raw (
    id SERIAL PRIMARY KEY,
    index_symbol VARCHAR(32) NOT NULL,
    trade_date DATE NOT NULL,
    component_symbol VARCHAR(32) NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'NDX_IC.csv',
    raw_payload JSONB NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_qd_nq100_ic_raw_key UNIQUE (index_symbol, trade_date, component_symbol)
);

CREATE INDEX IF NOT EXISTS idx_qd_nq100_ic_raw_trade_date
    ON qd_nq100_ic_raw(trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_qd_nq100_ic_raw_component_symbol
    ON qd_nq100_ic_raw(component_symbol);
