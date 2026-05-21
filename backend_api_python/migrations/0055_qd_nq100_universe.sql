-- UNIV-03: NQ100 point-in-time membership and change events (provenance: source, scraped_at)

CREATE TABLE IF NOT EXISTS qd_nq100_membership (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    source VARCHAR(64) NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qd_nq100_membership_valid_from ON qd_nq100_membership(valid_from);
CREATE INDEX IF NOT EXISTS idx_qd_nq100_membership_symbol ON qd_nq100_membership(symbol);
CREATE INDEX IF NOT EXISTS idx_qd_nq100_membership_pit_upper ON qd_nq100_membership ((COALESCE(valid_to, 'infinity'::date)));

CREATE TABLE IF NOT EXISTS qd_nq100_change_events (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    event_type VARCHAR(16) NOT NULL,
    effective_date DATE NOT NULL,
    source VARCHAR(64) NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_qd_nq100_change_events_event_type CHECK (event_type IN ('add', 'remove'))
);

CREATE INDEX IF NOT EXISTS idx_qd_nq100_change_events_effective_date ON qd_nq100_change_events(effective_date);
CREATE INDEX IF NOT EXISTS idx_qd_nq100_change_events_symbol ON qd_nq100_change_events(symbol);
