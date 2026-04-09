---
phase: 01-ibkr-data-source-implementation
plan: 05
subsystem: data_source
tags: [ibkr, integration, factory, exchange-id]
dependency_graph:
  requires:
    - 01-01
    - 01-02
    - 01-03
  provides:
    - INT-01
    - INT-02
    - INT-03
  affects:
    - backend_api_python/app/data_sources/factory.py
    - backend_api_python/app/services/price_fetcher.py
tech_stack:
  added: []
  patterns: [factory-pattern, parameter-priority]
key_files:
  created: []
  modified:
    - backend_api_python/app/data_sources/factory.py
    - backend_api_python/app/services/price_fetcher.py
decisions:
  - D-01: exchange_id parameter added to get_source()
  - D-02: 'ibkr-live' returns IBKRDataSource instance
  - D-03: Backward compatible when no exchange_id
  - D-08: exchange_id takes priority over market_category
  - D-14/D-15: PriceFetcher passes exchange_id to DataSourceFactory
---

# Phase 01 Plan 05: DataSourceFactory Integration Summary

**One-liner:** Integrate IBKRDataSource into DataSourceFactory with exchange_id priority

## Completed Tasks

| Task | Name | Status |
|------|------|--------|
| 1 | Update DataSourceFactory.get_source | Complete |
| 2 | Update PriceFetcher to pass exchange_id | Complete |

## Implementation Details

### Task 1: DataSourceFactory.get_source

```python
def get_source(cls, market: str, exchange_id: Optional[str] = None) -> BaseDataSource:
    if exchange_id == 'ibkr-live':
        if 'ibkr-live' not in cls._sources:
            from app.data_sources.ibkr import IBKRDataSource
            cls._sources['ibkr-live'] = IBKRDataSource()
        return cls._sources['ibkr-live']
```

- Added optional `exchange_id` parameter (default None)
- When `exchange_id='ibkr-live'`, returns IBKRDataSource
- Stored in `_sources` dict under key 'ibkr-live'
- Backward compatible: no exchange_id uses market parameter
- **exchange_id takes priority over market** per D-08

### Task 2: PriceFetcher passes exchange_id

```python
def fetch_current_price(self, market_category: str, symbol: str, exchange_id: Optional[str] = None):
    ticker = DataSourceFactory.get_ticker(market_category, symbol, exchange_id=exchange_id)
```

- Added `exchange_id` parameter to fetch_current_price()
- Passes exchange_id to DataSourceFactory.get_ticker()

## Verification

All verification checks passed in 01-VERIFICATION.md:
- ✅ DataSourceFactory.get_source accepts exchange_id
- ✅ exchange_id='ibkr-live' returns IBKRDataSource
- ✅ PriceFetcher accepts exchange_id parameter
- ✅ DataSourceFactory.get_ticker accepts exchange_id

## Deviations

None - plan executed as written.

---

## Self-Check: PASSED

- DataSourceFactory.get_source accepts exchange_id: YES
- exchange_id='ibkr-live' returns IBKRDataSource: YES
- exchange_id takes priority over market: YES
- PriceFetcher passes exchange_id to DataSourceFactory: YES
- All VERIFICATION.md checks pass: YES