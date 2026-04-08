# Coding Conventions

**Analysis Date:** 2026-04-08

## Naming Patterns

**Files:**
- snake_case: `price_fetcher.py`, `signal_processor.py`, `market.py`
- Test files: `test_price_fetcher.py`, `test_runners.py`

**Functions:**
- snake_case: `fetch_current_price`, `get_price_fetcher`, `process_signals`
- Private functions: prefixed with underscore `_wait_for_next_tick`, `_dedup_key`

**Variables:**
- snake_case: `price_cache`, `market_category`, `current_price`
- Constants: UPPER_CASE with underscores: `PRICE_CACHE_TTL_SEC`, `DEFAULT_USER_ID`

**Classes:**
- PascalCase: `PriceFetcher`, `SignalDeduplicator`, `KlineService`
- Abstract base classes: `BaseStrategyRunner`

**Types:**
- Type hints using Python typing module: `Optional[float]`, `Dict[str, Any]`, `List[Dict]`

## Code Style

**Formatting:**
- No explicit formatter configured; follows PEP 8 conventions
- Indentation: 4 spaces
- Maximum line length: not strictly enforced but reasonable (~100-120 chars)

**Linting:**
- Pylint: `# pylint: disable=protected-access` comments used in tests
- Type hints: Used extensively with `typing` module

**Code Organization:**
- One class or logical unit per file
- Related services grouped in `/app/services/`
- Routes in `/app/routes/`
- Strategies in `/app/strategies/`
- Data sources in `/app/data_sources/`

## Import Organization

**Order:**
1. Standard library: `import os`, `import time`, `from typing import Any`
2. Third-party: `import pytest`, `from unittest.mock import MagicMock`
3. Application: `from app.services.price_fetcher import PriceFetcher`
4. Internal: `from app.data_sources import DataSourceFactory`

**Path Aliases:**
- No explicit aliases configured; uses relative app imports

## Error Handling

**Patterns:**
- Try/except with broad `Exception` catching for non-critical failures
- Returns `None` on failure: `return None` or `(None, [])`
- Uses logger for non-critical errors: `logger.warning()`
- Guard clauses for early returns when validation fails

**Examples:**
```python
# From app/services/price_fetcher.py
try:
    with self._price_cache_lock:
        item = self._price_cache.get(cache_key)
        if item:
            price, expiry = item
            if expiry > now:
                return float(price)
except Exception:
    pass

# From app/services/signal_processor.py
except (ValueError, TypeError, KeyError):
    return False
```

**Error Returns:**
- Functions return `None` or empty collections when operations fail
- Tuple returns use `(None, [])` for "no result" cases

## Logging

**Framework:** Custom logger via `get_logger(__name__)` from `app.utils.logger`

**Patterns:**
- Use logger.warning for non-critical failures (e.g., price fetch failure)
- Use logger.error for critical failures
- Include contextual data: `"Failed to fetch price for %s:%s: %s"`

**Examples:**
```python
logger = get_logger(__name__)
logger.warning(
    "Failed to fetch price for %s:%s: %s",
    market_category,
    symbol,
    e,
)
```

## Comments

**When to Comment:**
- Explain complex logic and edge cases
- Document function purpose in docstrings (Google-style or basic)
- Comment test cases for clarity

**Docstrings:**
- Basic docstrings on public methods: `"""Get current price..."""`
- Args/Returns sections in key functions

**Test Comments:**
- Chinese comments in test files for test intent: `# 测试环境变量解析失败时的 fallback 逻辑`
- English comments in test methods: `# Should return cached price without calling get_ticker`

## Function Design

**Size:**
- Functions tend to be medium-sized with clear single responsibilities
- Complex logic broken into helper functions

**Parameters:**
- Use type hints for all parameters
- Default values for optional parameters: `market_category: str = "Crypto"`

**Return Values:**
- Explicit return types with type hints
- Return None for failure states: `-> Optional[float]`

## Module Design

**Exports:**
- Use explicit imports: `from app.services.price_fetcher import PriceFetcher`
- Singleton pattern for services: `get_price_fetcher()`, `get_signal_deduplicator()`

**Barrel Files:**
- `__init__.py` in each package for package-level imports
- Submodules explicitly imported in package `__init__.py`

## Class Design

**Constructor:**
- Explicit `__init__` with dependency injection
- Initialize caches and locks in `__init__`

**Inheritance:**
- Abstract base classes for strategy runners: `BaseStrategyRunner(ABC)`
- Use `@abstractmethod` for methods that must be implemented

**Patterns:**
- Thread-safe singletons with locks: `SignalDeduplicator`
- In-memory caches with TTL: `PriceFetcher._price_cache`

---

*Convention analysis: 2026-04-08*
