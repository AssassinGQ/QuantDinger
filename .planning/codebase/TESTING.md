# Testing Patterns

**Analysis Date:** 2026-04-09

## Python (Backend)

**Runner:**

- **pytest** (declared implicitly by use of `pytest` fixtures and marks; `requirements.txt` does not pin pytest—install dev deps as needed for local runs).
- **No `pytest.ini`, `tox.ini`, or `pyproject.toml`** test section found; discovery uses pytest defaults.

**Layout:**

- Primary suite: `backend_api_python/tests/`
- **Naming:** `test_*.py` (e.g. `test_signal_processor.py`, `test_ibkr_client.py`).
- **Subpackages:** e.g. `tests/live_trading/usmart/` with its own `conftest.py`.

**Shared fixtures (`backend_api_python/tests/conftest.py`):**

- Chinese module docstring describing shared pytest/fixture setup.
- Helper `make_db_ctx(...)` builds `MagicMock` context managers for DB connection patterns.
- Autouse fixture `reset_signal_deduplicator` clears in-memory dedup state between tests (`get_signal_deduplicator().clear()`).

**Patterns:**

- **`unittest.mock`:** `MagicMock`, `patch("module.path", ...)` for isolating `DataHandler`, config, or network (see `tests/test_signal_processor.py`).
- **Class-based grouping:** `class TestProcessSignals:` with `setup_method` for per-test instance state.
- **pytest fixtures:** `@pytest.fixture`, `@pytest.fixture(autouse=True)`, `@pytest.fixture(scope="module")` for expensive setup.
- **Integration tests:** `@pytest.mark.integration` (e.g. real IBKR connection in `tests/test_ibkr_client.py`); documented env vars (`IBKR_HOST`, `IBKR_PORT`) and example command in file comments.
- **Skip when unavailable:** `pytest.skip(...)` if live connection fails.

**Run commands (typical):**

```bash
cd backend_api_python
pytest tests/ -q
pytest tests/test_signal_processor.py -v
pytest tests/test_ibkr_client.py -v -m integration   # requires IBKR/TWS
```

**Coverage:**

- No enforced coverage threshold or `pytest-cov` config found in repository config files. Add locally if needed: `pytest --cov=app tests/`.

## Vue / JavaScript (Frontend)

**Runner:**

- **Jest** via `@vue/cli-plugin-unit-jest` (`quantdinger_vue/package.json` script `test:unit`: `vue-cli-service test:unit`).
- **Config:** `quantdinger_vue/jest.config.js` — `vue-jest` for SFCs, `babel-jest` for JS, asset stubbing, `@/` → `<rootDir>/src` mapping, snapshot serializer `jest-serializer-vue`.

**Test file locations (configured):**

- `**/tests/unit/**/*.spec.(js|jsx|ts|tsx)` and `**/__tests__/*.(js|jsx|ts|tsx)` per `testMatch` in `jest.config.js`.

**Current state:**

- **No `*.spec.js` / `*.spec.ts` files** were found under `quantdinger_vue/src` or `quantdinger_vue/tests` (only `tests/unit/.eslintrc.js`). The Jest pipeline is **wired but effectively unused** for component tests until specs are added.

**ESLint test env:**

- `quantdinger_vue/.eslintrc.js` `overrides` set `env.jest: true` for `**/__tests__/**` and `**/tests/unit/**/*.spec.*`.
- `quantdinger_vue/tests/unit/.eslintrc.js` sets `jest: true` for that folder.

## CI/CD

**Workflow:** `.github/workflows/basic-ci.yml`

- **Does not run pytest or Jest.**
- **Python job:** Install deps from `backend_api_python/requirements.txt` (MetaTrader5 line stripped for Linux), `py_compile` on `run.py`, `compileall` on `app/` and `scripts/`, then import check for `create_app`, `settings`, `health` (without calling `create_app()` to avoid DB/threads).
- **Frontend job:** Node 20, `yarn install --frozen-lockfile --ignore-scripts`, then `npm run lint:nofix` in `quantdinger_vue` (ESLint only).

**Implication:** Passing CI does not guarantee tests pass; run pytest and `yarn test:unit` locally before releases.

## Mocking Guidelines (Python)

- **Prefer patching at the import site used by the module under test** (e.g. `patch("app.services.signal_processor.DataHandler", ...)`).
- **Use shared DB mocks** from `conftest.make_db_ctx` when tests involve `get_db_connection` patterns.
- **Reset global singletons** via autouse fixtures when tests mutate process-wide state (deduplicator pattern).

## What to Add for New Code

| Area | Where | Pattern |
|------|--------|---------|
| New backend logic | `backend_api_python/tests/test_<feature>.py` | pytest + `unittest.mock`, classes per feature |
| Live / broker integration | Same file or `tests/live_trading/...` | `@pytest.mark.integration`, env-gated, `pytest.skip` on failure |
| New Vue components | `quantdinger_vue/tests/unit/` | Add `*.spec.js` matching Jest `testMatch`; mount with `@vue/test-utils` |

---

*Testing analysis: 2026-04-09*
