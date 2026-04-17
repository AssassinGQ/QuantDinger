---
phase: 01-ibkr-schedule-sufficiency-domain-model
plan: 01
subsystem: testing
tags: [ibkr, sufficiency, trading-hours, pytest]

requires: []
provides:
  - Typed DataSufficiencyResult / IBKRScheduleSnapshot contracts
  - IBKR schedule adapter over public trading_hours APIs
  - Public resolve_time_zone_id_for_schedule for explicit vs UTC fallback
affects: [phase-02-execution-guard]

tech-stack:
  added: []
  patterns:
    - "Adapter wraps trading_hours; domain types live in data_sufficiency_types"
    - "Timezone fallback metadata without importing private _resolve_tz"

key-files:
  created:
    - backend_api_python/app/services/data_sufficiency_types.py
    - backend_api_python/app/services/live_trading/ibkr_trading/ibkr_schedule_provider.py
    - backend_api_python/tests/test_data_sufficiency_types.py
    - backend_api_python/tests/test_ibkr_schedule_provider.py
    - backend_api_python/tests/test_data_sufficiency_integration.py
  modified:
    - backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py

key-decisions:
  - "Expose resolve_time_zone_id_for_schedule instead of duplicating _TZ_MAP in the adapter"
  - "TIMEFRAME_SECONDS_MAP aliases app.data_sources.base.TIMEFRAME_SECONDS for bar-duration parity"

patterns-established:
  - "Calendar schedule_status from parse_liquid_hours windows; session_open from is_rth_check for fuse alignment"

requirements-completed: [R1, R2, N2]

duration: 0min
completed: 2026-04-17
---

# Phase 01 Plan 01 Summary

**Established a typed sufficiency contract and an IBKR schedule adapter that reuse public ``trading_hours`` parsing/RTH checks without importing private symbols.**

## Self-Check: PASSED

- Key files exist; ``python3 -m pytest backend_api_python/tests`` passes (1155 passed).

## Accomplishments

- Added ``DataSufficiencyResult``, reason/status enums, diagnostics, and ``TIMEFRAME_SECONDS_MAP`` aligned with ``kline_fetcher`` bar seconds.
- Added ``get_ibkr_schedule_snapshot`` with explicit UTC clock injection, timezone-fallback warning path, and fuse-aware ``session_open``.
- Added ``resolve_time_zone_id_for_schedule`` to ``trading_hours`` for explicit vs ``fallback_utc`` resolution.

## Deviations

- None.
