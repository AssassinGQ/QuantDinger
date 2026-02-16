CREATE TABLE IF NOT EXISTS qd_kline_ranges (
    market VARCHAR(50) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    interval_sec INTEGER NOT NULL,
    min_ts BIGINT NOT NULL,
    max_ts BIGINT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (market, symbol, interval_sec)
);
