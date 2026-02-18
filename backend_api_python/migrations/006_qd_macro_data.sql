-- =============================================================================
-- 增量迁移 006: 宏观市场数据表 (qd_macro_data)
-- 存储 VIX/DXY/Fear&Greed 等日线级别宏观数据，供回测和活交易注入 df。
-- 数据源: yfinance (VIX/DXY), alternative.me (Fear&Greed)
-- 可重复执行。
-- =============================================================================

CREATE TABLE IF NOT EXISTS qd_macro_data (
    indicator VARCHAR(30) NOT NULL,   -- 'vix', 'dxy', 'fear_greed'
    date_val DATE NOT NULL,           -- 日期
    value DECIMAL(20,6) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (indicator, date_val)
);

CREATE INDEX IF NOT EXISTS idx_macro_data_lookup ON qd_macro_data(indicator, date_val DESC);
