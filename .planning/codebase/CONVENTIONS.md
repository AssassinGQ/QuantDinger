# Coding Conventions

**Analysis Date:** 2026-04-09

## Naming Patterns

**Python (`backend_api_python/`):**

- **Modules and packages:** `snake_case` (e.g. `signal_processor.py`, `db_postgres.py`).
- **Functions and methods:** `snake_case`.
- **Classes:** `PascalCase` (e.g. `SignalDeduplicator`, `DataHandler`).
- **Constants:** Typically `UPPER_SNAKE` in env-driven config; module-level strings follow existing style.
- **Private helpers:** Leading underscore where used (e.g. `_dedup_key`, `_apply_proxy_env` in `run.py`).

**Vue / JavaScript (`quantdinger_vue/src/`):**

- **Single-file components:** `PascalCase.vue` for feature components (e.g. `IndicatorCard.vue`, `BacktestModal.vue`); `index.vue` for route views in folders (e.g. `views/dashboard/index.vue`).
- **Route modules:** `kebab-case` paths under `views/` (e.g. `indicator-analysis/`, `trading-assistant/`).
- **Vue `export default`:** `name` property often matches folder/feature; options API with `data`, `methods`, `computed`, etc. (see `src/views/dashboard/index.vue`).

## Code Style

**Python:**

- No repo-wide `pyproject.toml`, `setup.cfg`, `ruff.toml`, or `flake8` config detected. Style is implicit PEP 8 with mixed **English and Chinese** docstrings and comments (module docstrings often Chinese-first for domain concepts).
- **Type hints:** Used in newer/refactored modules (`typing` imports: `Dict`, `List`, `Optional`, `Tuple`, `Any`); not uniformly applied across every legacy file.
- **String quotes:** Mix of double-quoted docstrings and f-strings; consistent per file.

**Vue / JavaScript:**

- **ESLint:** Root config `quantdinger_vue/.eslintrc.js` extends `plugin:vue/strongly-recommended` and `@vue/standard`.
- **Quotes:** Single quotes enforced (`quotes: ['single', ...]`).
- **Semicolons:** Disabled (`semi: 'never'`).
- **Indent:** ESLint `indent` off (delegated to editor / implicit Standard style).
- **Console:** `no-console` off (logging allowed in dev).
- **Parser:** `babel-eslint` in `parserOptions.parser` (legacy Vue 2 toolchain).

**CSS / Less:**

- `stylelint` scripts exist in `quantdinger_vue/package.json` (`lint:css`); no committed root `stylelint.config.*` found in glob search—config may live under `config/` or package defaults. Use existing Less variables and `::v-deep` patterns in `.vue` `<style lang="less" scoped>` blocks.

## Import Organization

**Python:**

- Standard library → third party → local `app.*` imports; grouping varies by file length.
- Lazy imports inside functions used to avoid cycles and heavy startup (e.g. `create_app` paths in `app/__init__.py`).

**Vue:**

- Webpack alias `@/` → `src/` (`vue.config.js` / Jest `moduleNameMapper`).
- Typical order: Vue / UI libs → `@/` utils, API, store → relative components.

## Error Handling

**Flask API (`backend_api_python/app/routes/`):**

- Route handlers often wrap logic in `try` / `except`, return `jsonify({...})` with HTTP status codes (`400`, `500`) and `success` / `error` keys for API consistency (e.g. `app/routes/mt5.py`).
- Optional integrations (e.g. MT5) catch `ImportError` and return JSON describing unavailability instead of crashing the process.

**Services / utilities:**

- `app/utils/safe_exec.py`: catches timeout, OOM, and execution errors; logs with `logger.error` and traceback where appropriate.
- Broad `except Exception` appears at process boundaries (startup helpers in `app/__init__.py`) with `logger.error(...)`.

**Vue:**

- **Axios:** Central `errorHandler` in `src/utils/request.js`—branches on `error.response.status` (401 clears storage and redirects to hash login; 403 shows demo notification).
- **Router:** `router/index.js` patches `push` to `.catch(err => err)` to avoid uncaught navigation duplicates.
- **Vuex:** `store/modules/user.js` and others use `.catch` on promises and `try`/`catch` around token parsing.

## Logging

**Configuration:**

- `app/utils/logger.py`: `setup_logger()` uses `logging.basicConfig`, optional `LOG_LEVEL` env (default `DEBUG`), rotating file `logs/app.log` via `RotatingFileHandler`.

**Usage pattern:**

- `logger = get_logger(__name__)` at module top (e.g. `app/__init__.py`).
- Levels: `debug` for diagnostics, `info` for lifecycle, `warning` for degraded behavior, `error` + traceback for failures (`app/utils/safe_exec.py`, `app/strategies/single_symbol_indicator.py`).

**Entrypoint:**

- `run.py` normalizes UTF-8 on Windows for stdout/stderr before logging-heavy output.

## Comments and Docstrings

**Python:**

- Module-level docstrings describe behavior; Chinese is common for product-specific terms.
- Inline comments explain non-obvious trading, threading, or Windows-specific behavior.
- Some comments reference tooling expectations (e.g. “Pylint needs these definitions” in `signal_processor.py`)—**automated Pylint is not configured in-repo**.

**Vue:**

- JSDoc-style block comments for non-trivial helpers (e.g. `getToken` in `request.js`).
- Template comments use `<!-- ... -->` for section grouping in large views.

## Function and Module Design

**Python:**

- Prefer **testable pure functions** where extracted (e.g. `position_state`, `is_signal_allowed` in `signal_processor.py` with tests in `tests/test_signal_processor.py`).
- **Singletons** documented in code (e.g. `SignalDeduplicator`, trading executor accessors in `app/__init__.py`).

**Vue:**

- Large page SFCs are acceptable in this codebase; prefer matching existing structure (template → script → scoped less) when extending.

---

*Convention analysis: 2026-04-09*
