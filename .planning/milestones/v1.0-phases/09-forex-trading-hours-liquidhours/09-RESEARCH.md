# Phase 9: Forex trading hours (liquidHours) - Research

**Researched:** 2026-04-11  
**Domain:** IBKR `ContractDetails.liquidHours` + pure `pytz` session math + `IBKRClient.is_market_open` integration  
**Confidence:** HIGH (codebase + IB official ContractDetails reference); MEDIUM (autouse patch stacking for “real” `is_rth_check` in `test_ibkr_client.py` — validate in implementation)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **生产代码不需要修改**——现有 `is_market_open` → `_create_contract(symbol, market_type="Forex")` → `reqContractDetailsAsync` → `is_rth_check(details, ...)` 链路已完整支持 Forex。
- **唯一的生产代码改动**：Forex 关市错误消息加专属提示（类似 Phase 7 的 qty=0 提示），让用户区分 Forex 24/5 关市和美股 RTH 关市。
- **Phase 9 核心交付物是 Forex 特有场景的测试覆盖**。
- IBKR Forex `liquidHours` 格式为跨日连续时段示例：`20260305:1715-20260306:1700`；`parse_liquid_hours` 已支持跨日，但此前无测试。
- 测试场景：工作日中间、周五 17:00 后、周六全天、周日 17:15 后、维护间隔(17:00–17:15)、节假日。
- 测试货币对：**EURUSD**、**GBPJPY**、**XAGUSD**。
- 测试层级：**纯逻辑** `trading_hours.py` + **集成** `IBKRClient.is_market_open`。
- **mock 模式**：复用 `_make_mock_ib_insync` + patch 模式。
- **fuse 机制**：保持现有设计，不对 Forex 做特殊处理。

### Claude's Discretion

- 具体测试用例 ID 和命名
- mock `liquidHours` 字符串的精确构造
- Forex 关市提示消息的具体措辞
- 使用 parametrize 或独立 test 方法

### Deferred Ideas (OUT OF SCOPE)

- （CONTEXT 中 **Deferred Ideas** 为 None — 无额外推迟项）
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RUNT-01 | `is_market_open` 对 Forex 合约使用 IBKR `liquidHours` 判断交易时间（24/5 特性） | 现有 `is_rth_check` 已消费 `details.liquidHours` + `timeZoneId`；本阶段用 **mock 合约详情 + 可控 `reqCurrentTimeAsync`** 锁定 Forex 行为；见 **Use Case Specifications** 与 **Architecture Patterns**。 |
</phase_requirements>

## Summary

Phase 9 不是重写交易时段引擎，而是**用 IBKR 返回的 `ContractDetails.liquidHours` / `timeZoneId`**（已在 `trading_hours.parse_liquid_hours` / `is_rth_check` 中实现）证明 **Forex 24/5、周末与节假日** 与 **美股 RTH 日历** 解耦。官方文档明确：`LiquidHours` 为交易所上的可交易时段字符串，TWS v970+ 在起止时间中包含**日期**以消除歧义（与当前解析器按 `YYYYMMDD`+`HHMM` 拆段一致）。

**交付重心（按 CONTEXT）：**  
（1）**测试**：跨日 `liquidHours`、Fri/Sun 边界、日内维护空档、`CLOSED` 节假日；EURUSD / GBPJPY / XAGUSD 三档代表性合约。  
（2）**小改动**：`market_type=="Forex"` 且 `is_rth_check` 为 False 时，在 `is_market_open` 返回的 `reason` 上追加 Forex 语境（与现有 `"outside RTH"` 文案并存或扩展）。

**Primary recommendation:** 以 **`now` 注入的单元测试**（`is_rth_check(..., now=...)`）覆盖边界；集成测试通过 **mock `reqContractDetailsAsync` / `reqCurrentTimeAsync`** 驱动真实 `is_rth_check`，并显式处理 `test_ibkr_client.py` 全局 `autouse` 对 `is_rth_check` 的 mock。

---

## Use Case Specifications

本节为 **新增测试用例的规格说明**（ID、输入、期望输出、边界、与成功标准映射）。实现时可拆为独立 `@pytest.mark.parametrize` 或分测试方法——属 **Claude's Discretion**。

### 成功标准映射

| 项目 | 含义 |
|------|------|
| **SC-1** | `is_market_open`（或等价路径）对 Forex 使用 **`liquidHours` / 合约元数据**（非硬编码美股日历）。 |
| **SC-2** | **周末与节假日**行为与 **IB Forex 式 schedule** 一致（mock 为跨日 + `CLOSED`），不依赖美股 RTH。 |
| **SC-3** | 测试包含 **Fri–Sun 等时间窗**，**mock `liquidHours`**。 |

---

### A. 纯逻辑层 — `test_trading_hours.py`

**前提：** 使用现有 `_make_details(liquid_hours, tz_id)` 与 `is_rth_check(..., now=tz.localize(...), con_id=...)`；`now` 传入可 **绕过 fuse**（见 `trading_hours.is_rth_check`），便于确定性断言。跨日用 **固定 2026-03** 的日期**，与现有测试风格一致。

**说明：** 下表示例 `liquidHours` 为**构造数据**，需与 `timeZoneId` 一致本地化；精确字符串以实现对齐为准。

| ID | 描述 | 输入（核心） | 期望输出 | 边界 / 备注 | 映射 |
|----|------|----------------|----------|----------------|------|
| **UC-FX-L01** | 跨日单段解析 | `liquidHours="20260308:1715-20260309:1700"`, `tz_id=EST`, `parse_liquid_hours` | 恰好 **1** 个 session；`start.date()!=end.date()` | 验证 start/end 各自带日期的 IB 格式 | SC-1, SC-3 |
| **UC-FX-L02** | 工作日“盘中”（周二下午，EST） | `liquidHours="20260310:0100-20260310:2300"`, `tz_id=EST`；`now` = **2026-03-10 14:00 US/Eastern**（周二） | `True` | 与跨日滚转（L01）解耦：证明 **周内日窗** 仍走 `liquidHours`；`server_time_utc` 可与 `now` 对齐任意合法 UTC | SC-1, SC-2 |
| **UC-FX-L03** | 周五 17:00 当周收盘后 | `liquidHours` 含 **20260306:…-20260306:1700**（周五）为当周最后 liquid 段；`now` = **Fri 2026-03-06 17:01 EST** | `False` | 边界：**17:00:00** 含于 `<= end` → `True`；**17:00:01** → `False`（可加 1 秒用例） | SC-2 |
| **UC-FX-L04** | 周六全天无交易 | 周六仅 `20260307:CLOSED` 或仅含不含周六的段；`now` = **Sat 2026-03-07 12:00 EST** | `False` | 与美股周末不同：此处 closed 来自 **FX schedule / CLOSED** | SC-2, SC-3 |
| **UC-FX-L05** | 周日 17:15 新一周开盘 | 段 `20260308:1715-20260309:1700`（Sun→Mon）；`now` = **Sun 2026-03-08 17:15 EST** | `True` | 再断言 **17:14** → `False`（维护/休市前一秒） | SC-2, SC-3 |
| **UC-FX-L06** | 日维护 17:00–17:15 | 两段：…`-20260309:1700`; `20260309:1715-20260310:1700`；`now` = **2026-03-09 17:05 EST** | `False` | 两段间 **无 session** 即 closed；不要求 IB 返回字面 `MAINT` | SC-2 |
| **UC-FX-L07** | 节假日 `CLOSED` | `20260325:CLOSED` 与相邻正常段混合；`now` 落在圣诞假日本日 | `False`；`parse_liquid_hours` 跳过含 `CLOSED` 的 segment | 与现有 `test_closed_day_skipped` 对齐，但 **明确 Forex 语境** | SC-2 |
| **UC-FX-L08** | GBPJPY + 非 EST `timeZoneId` | `tz_id=JST`，`liquidHours` 用 **东京本地**日期时间构造（仍 `YYYYMMDD:HHMM`）；`now` 在段内 / 段外各一断言 | `True` / `False` | 验证 `_resolve_tz` + `JST` 映射；**不**假设 FX 总在 EST | SC-1 |
| **UC-FX-L09** | XAGUSD 金属类窗口 | `tz_id=EST`（或与 IB mock 一致），`liquidHours` 用 **略短或不同** 的日窗（相对 EURUSD）；`now` 在窗内 | `True` | 与 L02 同逻辑，换字符串证明 **非股票专用** | SC-1 |

**回归：** 保留并运行现有 `TestParseLiquidHours` / `TestIsRTHCheck` / `TestFuse`（**REGR-01**）。

---

### B. 集成层 — `test_ibkr_client.py`

**前提：** `_make_client_with_mock_ib()` 已设置 `reqContractDetailsAsync` → `liquidHours` / `timeZoneId`，`reqCurrentTimeAsync` → UTC；**不得**依赖全局 `autouse` 将 `is_rth_check` 恒为 `True`。推荐新建类 **`TestForexRTHGate`**（或等价），在每个测试上：

- 使用 **`@patch("app.services.live_trading.ibkr_trading.trading_hours.is_rth_check", wraps=...)`** 导入真实 `is_rth_check` 并 wrap，**或**
- **`@patch(..., new=原始 is_rth_check)`**，确保覆盖 autouse mock。

| ID | 描述 | 输入（核心） | 期望输出 | 边界 / 备注 | 映射 |
|----|------|----------------|----------|----------------|------|
| **UC-FX-I01** | Forex + 跨日 `liquidHours` + 时间在内 | `is_market_open("EURUSD","Forex")`；mock `liquidHours` 跨日；`reqCurrentTimeAsync` → 对应 **UTC** 使 `now` 在段内 | `(True, "")` | 验证 **qualify → details → `is_rth_check`** 全链路 | SC-1 |
| **UC-FX-I02** | Forex + 周六 closed | 同上但 `liquidHours` 仅 `CLOSED` 或无可解析段；server 时间周六 | `(False, ...)`，`reason` 含 closed | 可与 L04 对齐的字符串 | SC-2, SC-3 |
| **UC-FX-I03** | GBPJPY + `timeZoneId=JST` | `symbol="GBPJPY"`，`Forex`；details 用 JST 段；server UTC 与之一致 | `(True, ...)` 或 `(False, ...)` 与单元一致 | 证明 **集成层不硬编码 EST** | SC-1 |
| **UC-FX-I04** | XAGUSD 全链路 | `XAGUSD` + 专用 `liquidHours` 字符串 | 与 mock 一致 open/closed | 三品种中 **贵金属** 代表 | SC-1 |
| **UC-FX-I05** | Forex 关市文案（生产改动后） | `market_type=Forex` 且 `is_rth_check` 判定 closed | `reason` **包含** Forex 提示子串（具体措辞 Discretion）；仍保留可识别的 closed 语义 | 可与 I02 合并或单独 mock | SC-1, SC-2 |

**回归：** 现有 `TestRTHGate`（AAPL + patch `is_rth_check`）保持不变 = **REGR-01**。

---

### C. 调用链与 fuse（验证级）

| ID | 描述 | 验证方式 | 映射 |
|----|------|----------|------|
| **UC-FX-R01** | `stateful_runner.pre_check` → `is_market_open` | **可选**：不新增测试；Phase 9 **CONTEXT** 已说明 fuse 不改为 Forex 特化；若加测，仅 **smoke** `market_category=Forex` + mock client | SC-2（行为一致即可） |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **Python** | 3.10+（项目） | 运行时 | 与 `backend_api_python` 一致 |
| **pytest** | 9.x（环境实测 9.0.2） | 单元 / 集成测试 | 现有套件 |
| **pytz** | 2025.2（环境实测） | `timeZoneId` → tz；`localize` | `trading_hours._resolve_tz` / session 比较 |
| **unittest.mock** | stdlib | `MagicMock` / `AsyncMock` / `@patch` | `test_ibkr_client` / `_make_details` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **ib_insync** | ≥0.9.86（requirements.txt） | 真实环境 IB | 本阶段 **不强制**；mock 为主 |

**Installation（开发）：** 以 `backend_api_python/requirements.txt` 为准；pytest 通常由 dev 环境提供。

**Version verification:** `pytest` / `pytz` 版本以执行环境 `pip show` 为准；发布前在 CI 镜像再确认一次。

---

## Architecture Patterns

### 数据流（Forex 与股票共用）

```
stateful_runner.pre_check
  → IBKRClient.is_market_open(symbol, market_type)
       → _create_contract(..., market_type)   # Forex → ib_insync.Forex / IDEALPRO
       → _qualify_contract_async
       → reqCurrentTimeAsync()                 # server_time UTC
       → reqContractDetailsAsync → details.liquidHours, details.timeZoneId
       → is_rth_check(details, server_time, con_id, symbol)  # 无 IB 调用
```

**RTH details 缓存：** `(con_id, server_time.date().isoformat())`（`client.py`）。集成测试应用 **固定 `reqCurrentTimeAsync`**，避免跨 UTC 日边界造成的缓存意外命中（见 Pitfalls）。

### Recommended test layout

```
tests/test_trading_hours.py   # 新增 class TestForexLiquidHours 或前缀 UC-FX-L**
tests/test_ibkr_client.py     # 新增 TestForexRTHGate + UC-FX-I**
```

### Pattern: 纯逻辑用 `now` 固定会话内时间

**What:** `is_rth_check(..., now=tz.localize(dt))`  
**When:** 所有 Forex 边界场景（避免 fuse / 真实 monotonic 时间）  
**Example:**

```python
# 与现有 test_trading_hours.TestIsRTHCheck.test_now_override_inside 一致
tz_ny = pytz.timezone("US/Eastern")
within = tz_ny.localize(datetime.datetime(2026, 3, 9, 14, 0))
assert is_rth_check(details, server_utc_any, now=within, con_id=1) is True
```

### Anti-patterns to avoid

- **用美股单日 `0930-1600` 字符串冒充 Forex** — 无法证明 RUNT-01 / SC-2。
- **在集成测试中忘记取消 autouse 对 `is_rth_check` 的 mock** — 会误判为始终 open。
- **手工实现“Forex 日历”** — 违背“以 IB `liquidHours` 为准”的要求。

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 解析 `liquidHours` | 第二套字符串解析 | `parse_liquid_hours` | 已处理 `CLOSED`、跨日、`;` 分段 |
| 会话内判断 | 在 `client` 里重写 RTH | `is_rth_check` | 单一真相；fuse 行为一致 |
| IB 时间转换 | 忽略 `timeZoneId` | `_resolve_tz` + `server_time_utc.astimezone(tz)` | 与 IB 文档一致 |

**Key insight:** RUNT-01 的“24/5”体现在 **IB 返回的段** 上，而不是在应用层复制一份 Forex 日历。

---

## Common Pitfalls

### Pitfall 1: `reqCurrentTimeAsync` 与 `liquidHours` 不一致

**What goes wrong:** `is_rth_check` 在 `now is None` 时用 `server_time_utc.astimezone(tz)` 作为 `now`（见 `trading_hours.py`）。集成测试若随意写 UTC，可能与 `liquidHours` 不匹配。  
**How to avoid:** 先选定 **目标本地时间** → 换算为 **UTC** 赋给 `reqCurrentTimeAsync`。  
**Warning signs:** 预期 open 却得到 closed，或反之。

### Pitfall 2: `_rth_details_cache` 跨测试泄漏

**What goes wrong:** `IBKRClient._rth_details_cache` 类级 dict 可能在多测试间保留。  
**How to avoid:** 新测试类 `setup_method` / fixture 清空 `IBKRClient._rth_details_cache`，或每测使用新 `client` 实例并统一 `conId`。

### Pitfall 3: 边界 inclusive

**What goes wrong:** `is_rth_check` 使用 `start <= now <= end`（闭区间）。  
**How to avoid:** 对 **17:00:00** 与 **17:00:01** 各断言一次（UC-FX-L03 / L06）。

### Pitfall 4: EST vs EDT

**What goes wrong:** 三月上旬可能为 **EST**（示例与现有测试一致用 `timeZoneId=EST` → `US/Eastern`）。  
**How to avoid:** 固定 **2026-03** 与文档化；若用夏令时日期，改用 `EDT` 或统一用 `US/Eastern` 本地化。

---

## Code Examples

### IBKR `LiquidHours` 格式（官方）

> TWS v970+：格式包含 **closing time 的日期** 以消除歧义，例如 `20180323:0930-20180323:1600;20180326:0930-20180326:1600`。  
> — [TWS API ContractDetails — LiquidHours](https://interactivebrokers.github.io/tws-api/classIBApi_1_1ContractDetails.html)

### 现有解析与检查（项目内）

```56:77:backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py
def parse_liquid_hours(liquid_hours: str, tz: pytz.BaseTzInfo) -> List[Tuple[datetime.datetime, datetime.datetime]]:
    """Parse IBKR liquidHours string into a list of (start, end) aware datetimes.

    Format: "20260305:0930-20260305:1600;20260306:0930-20260306:1600;20260307:CLOSED"
    """
    sessions = []
    for segment in liquid_hours.split(";"):
        segment = segment.strip()
        if not segment or "CLOSED" in segment.upper():
            continue
        # ...
```

```1030:1048:backend_api_python/app/services/live_trading/ibkr_trading/client.py
            server_time = await self._ib.reqCurrentTimeAsync()
            if server_time.tzinfo is None:
                server_time = server_time.replace(tzinfo=_pytz.UTC)

            con_id = getattr(contract, "conId", 0) or 0
            cache_key = (con_id, server_time.date().isoformat())
            details = self._rth_details_cache.get(cache_key)
            # ...
            if not is_rth_check(details, server_time, con_id=con_id, symbol=sym):
                return False, f"{sym} is outside RTH (market closed)"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 仅股票 `0930-1600` 测试 | Forex **跨日** + `CLOSED` + 维护空档 | Phase 9 规划中 | 证明非美股 RTH |
| 无 Forex 关市提示 | `market_type==Forex` 追加语境 | Phase 9 实施 | 运维可区分原因 |

**Deprecated/outdated:** 依赖 “周末 = 美股休市” 的隐含假设 — **不适用** IDEALPRO Forex（应以 `liquidHours` 为准）。

---

## Open Questions

1. **`_rth_details_cache` 使用 `server_time.date()`（UTC 日历日）是否会在极个别 UTC 边界造成与 IB 视角不一致？**  
   - *What we know:* 缓存按 `(conId, date)` 分日。  
   - *Recommendation:* Phase 9 测试用 **明确非边界** UTC；若未来 bug 报告，再评估改为按 `timeZoneId` 的本地日或缩短缓存。

2. **GBPJPY 的 IB `timeZoneId` 在 paper/live 是否常为 `JST`？**  
   - *What's unclear:* 合约实际返回值。  
   - *Recommendation:* mock 同时覆盖 **EST** 与 **JST** 即满足 RUNT-01，无需连真实 IB。

---

## Validation Architecture

> `workflow.nyquist_validation` 在 `.planning/config.json` 中为 **true** — 本段保留。

### Test Framework

| Property | Value |
|----------|--------|
| Framework | pytest（版本以环境为准） |
| Config file | 无统一 `pytest.ini` 检测 — 依赖默认 discovery |
| Quick run command | `cd backend_api_python && python3 -m pytest tests/test_trading_hours.py -q --tb=short -x` |
| Full suite command | `cd backend_api_python && python3 -m pytest tests/ -q`（或项目既有 CI 命令） |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| RUNT-01 | Forex `liquidHours` 驱动 open/closed | unit | `pytest tests/test_trading_hours.py -k "FX or Forex" -x` | 待新增 UC-FX-L** |
| RUNT-01 | `is_market_open` Forex 全链路 | integration | `pytest tests/test_ibkr_client.py -k "ForexRTH or forex_rth" -x` | 待新增 UC-FX-I** |

### Sampling Rate

- **Per task commit:** `pytest tests/test_trading_hours.py tests/test_ibkr_client.py::TestRTHGate -x`
- **Per wave merge:** 全量 `tests/`
- **Phase gate:** 全绿后再做 `/gsd:verify-work`

### Wave 0 Gaps

- [ ] 新增 `TestForexLiquidHours`（或等价）— 覆盖 UC-FX-L01–L09  
- [ ] 新增 `TestForexRTHGate` + 处理 **autouse `is_rth_check`** — UC-FX-I01–I05  
- [ ] 可选：`clear IBKRClient._rth_details_cache` fixture  

---

## Sources

### Primary (HIGH confidence)

- `backend_api_python/app/services/live_trading/ibkr_trading/trading_hours.py` — `parse_liquid_hours`, `is_rth_check`
- `backend_api_python/app/services/live_trading/ibkr_trading/client.py` — `is_market_open`, `_rth_details_cache`
- [IB TWS API — ContractDetails.LiquidHours / TimeZoneId](https://interactivebrokers.github.io/tws-api/classIBApi_1_1ContractDetails.html)

### Secondary (MEDIUM confidence)

- `backend_api_python/tests/test_trading_hours.py`, `test_ibkr_client.py` — 既有模式
- `.planning/phases/09-forex-trading-hours-liquidhours/09-CONTEXT.md` — 范围与交付物

### Tertiary (LOW confidence)

- 社区对 `liquidHours` 与真实交易所收盘偶有偏差的讨论 — **不纳入本阶段自动化**，以 mock 规格为准

---

## Metadata

**Confidence breakdown:**

- Standard stack: **HIGH** — 与仓库一致  
- Architecture: **HIGH** — 源码路径清晰  
- Pitfalls (cache / autouse): **MEDIUM** — 需在实现时验证 patch 顺序  

**Research date:** 2026-04-11  
**Valid until:** ~30 天（测试与文案稳定）；若 IB API 变更 `liquidHours` 格式则提前更新  

---

## RESEARCH COMPLETE

**Phase:** 09 — Forex trading hours (liquidHours)  
**Confidence:** **HIGH**（整体）；**MEDIUM**（`test_ibkr_client` 中真实 `is_rth_check` 与 autouse 交互）

### Key Findings

- **RUNT-01** 已由 `is_rth_check(details.liquidHours, timeZoneId)` 满足；Phase 9 价值在于 **Forex 形制的 `liquidHours` + 集成路径测试** 与 **关市文案**。
- IB 官方文档支持 **v970+ 起止日期分段**，与 `parse_liquid_hours` 实现一致。
- **新增用例规格** 以 **UC-FX-L01–L09**（逻辑）与 **UC-FX-I01–I05**（集成）为主，映射 **SC-1–SC-3**。
- **autouse** `_always_rth` 会遮蔽真实 `is_rth_check` — 新增集成测试必须 **显式 patch / wraps**。

### File Created

`.planning/phases/09-forex-trading-hours-liquidhours/09-RESEARCH.md`

### Ready for Planning

Research complete. Planner can create `09-01-PLAN.md` and task breakdown from **Use Case Specifications** and **Standard Stack**.
