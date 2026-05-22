-- Phase 20-A Step A: IndexETF market category seed
-- Adds ETF metadata columns and the first batch of 18 index ETFs covering
-- US (QQQ/SPY/DIA/IWM/VTI), inverse/leveraged (SQQQ/SH/TQQQ),
-- A-share (510300/510500/588000/159915/510050), HK (02800/03033),
-- and cross-border (EWJ/FXI/EFA/VWO).
--
-- Idempotent: safe to re-run.

-- 1. Extend qd_market_symbols with ETF-specific metadata
ALTER TABLE qd_market_symbols
    ADD COLUMN IF NOT EXISTS is_inverse INTEGER DEFAULT 0;

ALTER TABLE qd_market_symbols
    ADD COLUMN IF NOT EXISTS leverage NUMERIC(4,2) DEFAULT 1.0;

ALTER TABLE qd_market_symbols
    ADD COLUMN IF NOT EXISTS underlying_index VARCHAR(64) DEFAULT '';

-- 2. Seed first batch of IndexETF symbols
INSERT INTO qd_market_symbols
    (market, symbol, name, exchange, currency, is_active, is_hot, sort_order,
     is_inverse, leverage, underlying_index)
VALUES
    -- US flagship ETFs (YFinance / IBKR SMART)
    ('IndexETF', 'QQQ',  'Invesco QQQ Trust (Nasdaq 100)',           'NASDAQ', 'USD', 1, 1, 100, 0,  1.0, 'NDX'),
    ('IndexETF', 'SPY',  'SPDR S&P 500 ETF (S&P 500)',               'ARCA',   'USD', 1, 1,  99, 0,  1.0, 'SPX'),
    ('IndexETF', 'DIA',  'SPDR Dow Jones Industrial (Dow 30)',       'ARCA',   'USD', 1, 1,  98, 0,  1.0, 'DJI'),
    ('IndexETF', 'IWM',  'iShares Russell 2000 (Small Cap)',         'ARCA',   'USD', 1, 1,  97, 0,  1.0, 'RUT'),
    ('IndexETF', 'VTI',  'Vanguard Total Stock Market',              'ARCA',   'USD', 1, 1,  96, 0,  1.0, 'CRSP US Total'),
    -- Inverse / Leveraged (for shorting indices)
    ('IndexETF', 'SQQQ', 'ProShares UltraPro Short QQQ (-3x)',       'NASDAQ', 'USD', 1, 1,  90, 1, -3.0, 'NDX'),
    ('IndexETF', 'SH',   'ProShares Short S&P 500 (-1x)',            'ARCA',   'USD', 1, 1,  89, 1, -1.0, 'SPX'),
    ('IndexETF', 'TQQQ', 'ProShares UltraPro QQQ (3x)',              'NASDAQ', 'USD', 1, 0,  88, 0,  3.0, 'NDX'),
    -- A-share ETFs (akshare fund_etf_hist_em)
    ('IndexETF', '510300', '沪深300ETF (华泰柏瑞)',                    'SSE',    'CNY', 1, 1,  80, 0,  1.0, 'CSI300'),
    ('IndexETF', '510500', '中证500ETF (南方)',                        'SSE',    'CNY', 1, 1,  79, 0,  1.0, 'CSI500'),
    ('IndexETF', '588000', '科创50ETF (华夏)',                         'SSE',    'CNY', 1, 1,  78, 0,  1.0, 'STAR50'),
    ('IndexETF', '159915', '创业板ETF (易方达)',                       'SZSE',   'CNY', 1, 1,  77, 0,  1.0, 'ChiNext'),
    ('IndexETF', '510050', '上证50ETF',                                'SSE',    'CNY', 1, 1,  76, 0,  1.0, 'SSE50'),
    -- HK ETFs (akshare / yfinance / Tencent)
    ('IndexETF', '02800',  '盈富基金 (恒生指数)',                       'SEHK',   'HKD', 1, 1,  70, 0,  1.0, 'HSI'),
    ('IndexETF', '03033',  '南方恒生科技ETF',                           'SEHK',   'HKD', 1, 1,  69, 0,  1.0, 'HSTECH'),
    -- Cross-border / global (YFinance)
    ('IndexETF', 'EWJ',  'iShares MSCI Japan',                       'ARCA',   'USD', 1, 0,  60, 0,  1.0, 'MSCI Japan'),
    ('IndexETF', 'FXI',  'iShares China Large-Cap',                  'ARCA',   'USD', 1, 0,  59, 0,  1.0, 'FTSE China 50'),
    ('IndexETF', 'EFA',  'iShares MSCI EAFE',                        'ARCA',   'USD', 1, 0,  58, 0,  1.0, 'MSCI EAFE'),
    ('IndexETF', 'VWO',  'Vanguard Emerging Markets',                'ARCA',   'USD', 1, 0,  57, 0,  1.0, 'FTSE EM')
ON CONFLICT (market, symbol) DO NOTHING;
