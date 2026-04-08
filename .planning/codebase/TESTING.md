# Testing Patterns

**Analysis Date:** 2026-04-08

## Test Framework

**Runner:**
- pytest (imported in all test files)
- No explicit version constraint found in requirements.txt
- Config: No `pytest.ini` or `pyproject.toml` configuration found; uses pytest defaults

**Assertion Library:**
- pytest assertions: `assert condition`, `assert value == expected`
- unittest.mock for mocking: `from unittest.mock import MagicMock, patch`

**Run Commands:**
```bash
pytest backend_api_python/tests/           # Run all tests
pytest backend_api_python/tests/ -v       # Verbose output
pytest backend_api_python/tests/ -k test_name  # Run specific test
```

## Test File Organization

**Location:**
- Tests co-located in `backend_api_python/tests/` directory
- Test files use `test_*.py` naming pattern: `test_price_fetcher.py`, `test_runners.py`

**Naming:**
- Test file names match module being tested: `test_signal_processor.py`, `test_price_fetcher.py`
- Test classes use `Test` prefix: `class TestPriceFetcher`, `class TestSignalProcessor`
- Test methods use `test_` prefix: `test_fetch_current_price_success()`

**Structure:**
```
backend_api_python/tests/
├── test_price_fetcher.py
├── test_signal_processor.py
├── test_runners.py
├── test_indicator_group.py
├── test_signal_deduplicator.py
├── conftest.py
└── live_trading/
    └── usmart/
        └── test_usmart_*.py
```

## Test Structure

**Suite Organization:**
```python
# From test_price_fetcher.py
class TestPriceFetcher:
    def test_fetch_current_price_success(self):
        # Arrange
        fetcher = PriceFetcher()
        
        # Act
        with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
            mock_ticker.return_value = {"last": 100.0}
            price = fetcher.fetch_current_price(None, "BTC/USDT", market_category="Crypto")
            
        # Assert
        assert price == 100.0
        mock_ticker.assert_called_once_with("Crypto", "BTC/USDT")
```

**Patterns:**
- Setup in `setup_method()` for test class initialization
- Act via direct method calls with mocked dependencies
- Assert using pytest assertions

**Fixtures (from conftest.py):**
```python
@pytest.fixture(autouse=True)
def reset_signal_deduplicator():
    """每个测试前清空内存去重缓存，避免互相干扰。"""
    get_signal_deduplicator().clear()

def make_db_ctx(
    fetchone_result=None,
    fetchall_result=None,
    lastrowid=None,
    fetchone_side_effect=None,
):
    """构造 get_db_connection 的 context manager mock"""
    conn = MagicMock()
    cursor = MagicMock()
    # ... configuration
    return ctx
```

## Mocking

**Framework:** unittest.mock (MagicMock, patch)

**Patterns:**
```python
# Patching module-level dependencies
from unittest.mock import patch, MagicMock

with patch("app.services.price_fetcher.DataSourceFactory.get_ticker") as mock_ticker:
    mock_ticker.return_value = {"last": 100.0}
    price = fetcher.fetch_current_price(None, "BTC/USDT", market_category="Crypto")
    assert price == 100.0

# Using MagicMock for complex objects
runner.price_fetcher = MagicMock()
runner.price_fetcher.fetch_current_price.return_value = None
```

**What to Mock:**
- External services: DataSourceFactory, database connections
- Third-party libraries: ib_insync, ccxt
- Network calls: API requests
- Heavy dependencies: jwt, psycopg2 (mocked in indicator tests)

**What NOT to Mock:**
- Simple utility functions
- Pure business logic without external dependencies
- Internal method calls within same module (unless testing isolation)

## Fixtures and Factories

**Test Data:**
```python
# From test_signal_processor.py
def test_process_signals_with_tp_sl(self):
    dh = MagicMock()
    dh.get_current_positions.return_value = [{"side": "long", "size": 0.1}]
    sig = {"type": "add_long", "position_size": 0.1, "timestamp": int(time.time())}
    risk_sig = {"type": "close_long", "reason": "tp", "timestamp": int(time.time())}
```

**Location:**
- Shared fixtures in `backend_api_python/tests/conftest.py`
- Test-specific fixtures defined in test files using `@pytest.fixture`

**Mocking Database (from conftest.py):**
```python
def make_db_ctx(
    fetchone_result=None,
    fetchall_result=None,
    lastrowid=None,
    fetchone_side_effect=None,
):
    conn = MagicMock()
    cursor = MagicMock()
    if fetchone_side_effect is not None:
        cursor.fetchone.side_effect = fetchone_side_effect
    else:
        cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result if fetchall_result is not None else []
    cursor.lastrowid = lastrowid
    conn.cursor.return_value = cursor
    ctx = MagicMock()
    ctx.__enter__.return_value = conn
    ctx.__exit__.return_value = False
    return ctx
```

## Coverage

**Requirements:** None enforced

**View Coverage:**
```bash
# Not configured - no coverage tool
```

No explicit coverage target or reporting configured in repository.

## Test Types

**Unit Tests:**
- Most tests are unit tests testing individual services/functions
- Examples: `test_price_fetcher.py`, `test_signal_processor.py`, `test_signal_deduplicator.py`
- Mock all external dependencies

**Integration Tests:**
- Some tests integrate Flask routes with test client: `test_indicator_group.py`
- Uses Flask test client to test API endpoints
- Database connections mocked with `make_db_ctx`

**E2E Tests:**
- Not detected; no Selenium or Playwright tests found

## Common Patterns

**Async Testing:**
- Uses `unittest.mock.patch("time.sleep")` to mock sleep in tests
- Example from test_runners.py:
```python
with patch(
     "app.strategies.runners.base_runner.BaseStrategyRunner.is_running",
     side_effect=[True, False]
 ), patch(
     "app.strategies.runners.base_runner.BaseStrategyRunner._wait_for_next_tick",
     return_value=(False, 0, 0)
 ), patch("time.sleep"):
    runner.run(1, {}, MagicMock(), None)
```

**Error Testing:**
```python
def test_fetch_current_price_handles_exception(self):
    fetcher = PriceFetcher()
    
    with patch("app.services.price_fetcher.DataSourceFactory.get_ticker", side_effect=Exception("API Error")):
        price = fetcher.fetch_current_price(None, "FAIL/USDT")
        
        assert price is None
```

**Singleton Reset (from conftest.py):**
```python
@pytest.fixture(autouse=True)
def reset_signal_deduplicator():
    """每个测试前清空内存去重缓存，避免互相干扰。"""
    get_signal_deduplicator().clear()
```

**Database Mocking:**
```python
@pytest.fixture
def client():
    from flask import Flask, g
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(ind_mod.indicator_bp, url_prefix="/api/indicator")
    
    @app.before_request
    def _set_g_user():
        g.user_id = 1
    
    with app.test_client() as c:
        yield c
```

**Flask Route Testing:**
- Uses Flask test client for endpoint testing
- Uses `@app.before_request` to set up request context (e.g., user ID)
- Mocks database connections with custom context manager

---

*Testing analysis: 2026-04-08*
