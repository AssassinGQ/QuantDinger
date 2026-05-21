# Phase 13: Qualify result caching + E2E prefix fix - Research

**Researched:** 2026-04-11  
**Domain:** IBKR `qualifyContractsAsync` caching, Flask E2E route alignment  
**Confidence:** HIGH (codebase-verified); MEDIUM (IB API edge cases — paper validation deferred)

## Summary

Phase 13 adds an **in-memory, per-`IBKRClient` instance** cache for successful contract qualification so repeated calls for the same **(symbol, market_type)** within a configurable TTL avoid extra `qualifyContractsAsync` round-trips. Implementation should live in or immediately around `_qualify_contract_async` in `client.py` so all current call sites (`place_market_order`, `place_limit_order`, `is_market_open`, `get_quote`) benefit without duplicating logic.

**Locked decisions from discuss-phase** (see `<user_constraints>`): **do not** clear the qualify cache on IBKR reconnect; rely on TTL plus targeted invalidation on qualify/validation failures. Per-market TTLs (Forex / USStock / HShare), memory-only storage, and cache key `(symbol, market_type)` are fixed choices.

**E2E drift:** production registers `strategy_bp` with `url_prefix='/api'` (`app/routes/__init__.py`), while `test_forex_ibkr_e2e.py` uses `url_prefix="/api/strategy"`, so URLs are one segment off (`/api/strategy/strategies/...` vs `/api/strategies/...`). Fixing the fixture to `/api` and updating request paths aligns tests with production routing.

**Primary recommendation:** Extend `_qualify_contract_async` to accept `market_type` and the logical **cache symbol** (the same string used in order APIs) for keying; on cache hit, copy cached qualification fields onto the freshly created contract before returning; add unit tests that assert `qualifyContractsAsync` call count. For E2E, change blueprint prefix to `/api` and POST `/api/strategies/create`; optionally factor a tiny test app factory that mirrors `register_routes`’ strategy registration without pulling full `create_app` DB startup unless tests require it.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**缓存策略与 TTL**
- TTL 中等时长（5-15 分钟），具体默认值 Claude 决定
- TTL 按 market 分开可配：Forex / USStock / HShare 各自独立 TTL
- Cache key 使用 `symbol + market_type` 组合
- 内存缓存（IBKRClient 实例级别），不需要外部缓存
- 失败模式安全：过期缓存数据最多导致 IBKR 拒单，不会静默执行错误交易

**缓存失效触发**
- IBKR 重连时**不清除**缓存 — conId 是全局统一的，不随 gateway 变化，TTL 自然过期足够
- 特定错误码（如 qualify 失败、合约无效）**清除对应 symbol** 的缓存条目
- 不需要手动清缓存的 API 或端点

**E2E prefix 修复**
- 中等范围修复：修正 `test_forex_ibkr_e2e.py` 的 `url_prefix` 从 `/api/strategy` 改为 `/api`（匹配生产 `register_routes`），同时重构 Flask test app 创建逻辑使其更接近生产 `create_app`
- 修改后运行全部 E2E 测试确认不破坏现有用例
- 不在 Phase 13 新增 E2E 测试用例 — 新用例留给 Phase 18

### Claude's Discretion

- TTL 具体默认值（5-15 分钟范围内）
- 缓存实现方式（dict + timestamp、functools.lru_cache 变体、或自定义类）
- 需要触发缓存清除的具体 IBKR 错误码列表
- Flask test app 重构的具体方式（复用 create_app 的哪些部分）

### Deferred Ideas (OUT OF SCOPE)

- **Phase 18 E2E 覆盖 qualify cache 场景** — 用户要求在 Phase 18 路线图中明确标注：cache hit / cache miss / cache invalidation（错误码触发）的 E2E 测试用例
- **重连清缓存** — 当前决定不清，如果未来发现 TTL + 错误码失效不够，可在后续 phase 加入
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **INFRA-01** | `qualifyContractsAsync` 结果按 symbol 缓存（TTL 可配）；*REQUIREMENTS.md* 原文还写「IBKR 重连时自动失效全部缓存」 | **Implement per CONTEXT.md:** reconnect does **not** clear cache; TTL + per-symbol invalidation on bad qualify/validation. Planner should note REQUIREMENTS vs CONTEXT conflict and treat CONTEXT as authoritative for Phase 13 (consider amending REQUIREMENTS.md in implementation wave). |
| **TEST-01** | `test_forex_ibkr_e2e.py` blueprint prefix 与生产一致 | Use `url_prefix='/api'`; paths become `/api/strategies/...` per `strategy.py` routes. |
</phase_requirements>

## Standard Stack

### Core

| Library / piece | Version | Purpose | Why Standard |
|-----------------|---------|---------|--------------|
| Python | 3.10+ (project) | Runtime | Matches `backend_api_python` |
| ib_insync | (project `requirements.txt`) | `IB.qualifyContractsAsync(contract)` | Already integrated; mutates contract in place |
| Flask | (project) | E2E test client | Existing E2E pattern |

### Supporting

| Approach | Purpose | When to Use |
|----------|---------|-------------|
| `dict` + monotonic expiry timestamps | Per-entry TTL without new deps | CONTEXT allows; no `cachetools` in repo today |
| Env vars e.g. `IBKR_QUALIFY_TTL_FOREX_SEC` (names TBD) | Operator-tunable TTL | Satisfies “configurable and documented for operators” |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled dict+TTL | `cachetools.TTLCache` | Fewer lines, extra dependency — only worth it if TTL logic grows complex |

**Installation:** No new packages required for minimal dict-based cache (verify with `pip` / `requirements.txt` before adding anything).

**Version verification:** Run `pip show ib_insync` in `backend_api_python` venv when implementing (pinned in project requirements).

## Architecture Patterns

### Recommended integration point

`_qualify_contract_async` today:

```851:856:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    async def _qualify_contract_async(self, contract) -> bool:
        try:
            return len(await self._ib.qualifyContractsAsync(contract)) > 0
        except Exception as e:
            logger.warning("Contract qualification failed: %s", e)
            return False
```

**Pattern:** Callers always build the contract with `_create_contract(symbol, market_type)` immediately before qualify. For a cache key matching CONTEXT (`symbol + market_type`), thread **`market_type`** and the **logical symbol** (e.g. `EURUSD`, not necessarily `localSymbol`) into `_qualify_contract_async` — the current signature has **only** `contract`, so the planner should add parameters (or a small dataclass) to avoid ambiguous keys derived from partially filled contracts.

**Call sites to keep consistent (4):**

- `is_market_open` — uses `_qualify_contract_async(contract)` in a retry loop (`client.py` ~1047)
- `place_market_order` — ~1125
- `place_limit_order` — ~1203
- `get_quote` — ~1425

### Cache hit behavior

**What:** On hit, apply stored fields to the **new** contract object (`conId`, `localSymbol`, `secType`, `exchange`, `currency` as needed for downstream `_validate_qualified_contract` and orders) without calling `qualifyContractsAsync`.

**When to use:** Same `(cache_symbol, market_type)` within TTL and no invalidation flag.

**Anti-patterns to avoid**

- **Caching without `market_type` in the key:** US vs HK vs Forex for the same ticker symbol string could collide — forbidden by CONTEXT.
- **Clearing cache in `_on_connected`:** Explicitly out of scope per CONTEXT (reconnect handling differs from `.planning/REQUIREMENTS.md` INFRA-01 text — resolve in docs/plan).
- **Caching failed qualifies:** Do not cache negative results unless explicitly designed with short TTL; CONTEXT emphasizes invalidation on qualify failure (clear entry).

### Reconnect hooks (informational)

```540:546:backend_api_python/app/services/live_trading/ibkr_trading/client.py
    def _on_connected(self):
        logger.info("[IBKR-Event] connectedEvent — connection established")

    def _on_disconnected(self):
        logger.warning("[IBKR-Event] disconnectedEvent — connection lost")
        self._events_registered = False
        self._schedule_reconnect()
```

No qualify-cache clear here per CONTEXT.

### E2E routing alignment

Production:

```37:37:backend_api_python/app/routes/__init__.py
    app.register_blueprint(strategy_bp, url_prefix='/api')
```

Strategy routes are defined as `/strategies/create`, etc.:

```64:64:backend_api_python/app/routes/strategy.py
@strategy_bp.route('/strategies/create', methods=['POST'])
```

So the full path is **`/api/strategies/create`**, not `/api/strategy/strategies/create`.

Current E2E fixture:

```78:88:backend_api_python/tests/test_forex_ibkr_e2e.py
@pytest.fixture
def client_fixture():
    """Minimal Flask app with strategy routes; g.user_id set for UC-SA-E2E API tests."""
    app = Flask(__name__)
    app.register_blueprint(strategy_bp, url_prefix="/api/strategy")

    @app.before_request
    def set_g():
        g.user_id = 1

    with app.test_client() as c:
        yield c
```

**Pattern for “closer to create_app”:** Minimal app + `register_blueprint(strategy_bp, url_prefix='/api')` matches production registration. Full `create_app()` also runs DB init, workers, and all blueprints — usually unnecessary for this E2E file if imports stay patched; discretion per CONTEXT.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-order qualify deduplication scattered in 4 methods | Copy-paste cache checks | Single helper used by `_qualify_contract_async` | One behavior, one test surface |
| Custom IB discovery | Reinvent qualify | `qualifyContractsAsync` | IB contract resolution is non-trivial |

**Key insight:** `qualifyContractsAsync` mutates the contract in place; cache entries should store the fields needed to reconstruct qualification state on a **new** contract instance created by `_create_contract`.

## Common Pitfalls

### Pitfall 1: REQUIREMENTS vs CONTEXT on reconnect
**What goes wrong:** Implementing full cache clear on reconnect because INFRA-01 in `REQUIREMENTS.md` says so, conflicting with Phase 13 CONTEXT.  
**How to avoid:** Treat CONTEXT as the phase contract; update REQUIREMENTS traceability or INFRA-01 wording in a doc fix when implementing.  
**Warning signs:** Plan tasks mentioning `_on_connected` cache flush.

### Pitfall 2: Wrong cache key symbol
**What goes wrong:** Using `contract.localSymbol` only — may differ from strategy `symbol` string and collide across markets.  
**How to avoid:** Key with explicit `(logical_symbol, market_type)` passed from the order/RTH/quote API.

### Pitfall 3: Stale contract fields on cache hit
**What goes wrong:** Skipping `_validate_qualified_contract` or missing fields so `placeOrder` sees invalid `conId`.  
**How to avoid:** On hit, populate all fields `_validate_qualified_contract` checks (`conId`, `secType`).

### Pitfall 4: E2E URL replace misses
**What goes wrong:** Changing prefix but leaving old path strings.  
**How to avoid:** Grep `test_forex_ibkr_e2e.py` for `/api/strategy` and docstrings.

## Code Examples

### Production-like strategy URL

- Create: `POST /api/strategies/create` (not `/api/strategy/strategies/create`).

### Qualify call-count test (conceptual)

Use `AsyncMock` / function wrapper counting invocations on `client._ib.qualifyContractsAsync`; call `place_market_order` twice with same symbol/market_type within TTL; assert second call does not increment qualify count (exact assertion depends on implementation).

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| E2E `/api/strategy/...` | `/api/strategies/...` | Matches `register_routes` |
| Always qualify per order | TTL cache with invalidation | Reduces IB API load |

**Deprecated/outdated:** N/A for this phase.

## Open Questions

1. **REQUIREMENTS.md INFRA-01 vs CONTEXT (reconnect)**
   - What we know: Phase CONTEXT explicitly rejects reconnect invalidation; REQUIREMENTS still says reconnect invalidates.
   - Recommendation: Follow CONTEXT for implementation; reconcile REQUIREMENTS text in the same PR or immediately after.

2. **Exact IB error codes for invalidation**
   - What we know: CONTEXT leaves the list to discretion; `_qualify_contract_async` currently treats empty qualify and exceptions as failure.
   - Recommendation: Start with “clear on empty qualify, clear on validation failure after qualify, clear on logged qualify exception”; expand to `error` event codes if needed.

3. **Default TTL values**
   - What we know: 5–15 minutes per market; pick one default per category in range.
   - Recommendation: e.g. **600 seconds (10 min)** as a single default for all three unless differentiated env vars are set (document in operator notes / env sample).

## Validation Architecture

> `workflow.nyquist_validation` is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (project standard) |
| Config file | `tests/conftest.py` (shared fixtures; no root `pytest.ini` in repo) |
| Quick run (qualify tests) | `cd backend_api_python && python -m pytest tests/test_ibkr_client.py::TestQualifyContractForex -q` |
| E2E module | `python -m pytest tests/test_forex_ibkr_e2e.py -q` |
| Full suite | `cd backend_api_python && python -m pytest` (per STATE.md ~928 tests gate) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File |
|--------|----------|-----------|-------------------|------|
| INFRA-01 | Second request within TTL skips `qualifyContractsAsync` | unit (mock IB) | `pytest tests/test_ibkr_client.py -k qualify -x` (extend with new tests) | Add/extend `test_ibkr_client.py` |
| INFRA-01 | TTL / per-market config readable | unit or smoke | Env set in test + assert effective TTL | TBD in plan |
| INFRA-01 | Invalidation on bad qualify | unit | Mock empty qualify → cache cleared for key | New |
| TEST-01 | Blueprint matches production | integration (Flask client) | `pytest tests/test_forex_ibkr_e2e.py -q` | Existing file, path fixes |

### Sampling Rate

- **Per task commit:** targeted `pytest` on touched tests.
- **Phase gate:** full backend suite green (per STATE.md).

### Wave 0 Gaps

- [ ] New tests for qualify cache hit/miss/invalidate (unit) — **not** full E2E in Phase 13 per CONTEXT (Phase 18).
- [ ] Operator doc snippet (env vars for TTL) — location TBD (`README`, deploy doc, or `CLAUDE.md` for QuantDinger subproject if added).

## Sources

### Primary (HIGH confidence)

- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — qualify, reconnect, order paths
- `backend_api_python/app/routes/__init__.py` — blueprint prefixes
- `backend_api_python/app/routes/strategy.py` — route paths
- `backend_api_python/tests/test_forex_ibkr_e2e.py` — current E2E prefix
- `.planning/phases/13-qualify-result-caching-e2e-prefix-fix/13-CONTEXT.md` — locked decisions

### Secondary (MEDIUM confidence)

- ib_insync: `qualifyContractsAsync` mutates contracts — consistent with existing tests in `test_ibkr_client.py`

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — matches existing dependencies
- Architecture: **HIGH** — file/line references verified
- Pitfalls: **MEDIUM** — REQUIREMENTS conflict documented; IB edge cases need runtime validation

**Research date:** 2026-04-11  
**Valid until:** ~30 days (or until IBKR client refactor)
