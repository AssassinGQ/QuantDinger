# 测试模式与覆盖现状（Quality Focus）

**分析日期：** 2026-04-22

## 测试框架

**后端（Python）：**
- Runner：`pytest`（大量 `import pytest` 与 `@pytest.mark` 证据位于 `backend_api_python/tests/`，如 `backend_api_python/tests/test_ibkr_client.py`）。
- 共享配置：`backend_api_python/tests/conftest.py`（定义 `pytest_configure` marker 与通用 fixture）。
- Mock 工具：`unittest.mock`（`MagicMock`/`patch` 在 `backend_api_python/tests/test_ibkr_order_callback.py`、`backend_api_python/tests/test_ibkr_client.py` 中高频使用）。

**前端（Vue 2）：**
- Runner：Jest（`quantdinger_vue/jest.config.js`）。
- 组件测试：`@vue/test-utils`（`shallowMount` 用于组件挂载，见 `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。
- 断言：Jest `expect(...)`（见 `quantdinger_vue/tests/unit/*.spec.js`）。

## 运行命令（当前仓库可见）

```bash
cd quantdinger_vue && npm run test:unit      # 前端单元测试（package.json 已定义）
cd quantdinger_vue && npm run lint:nofix     # 前端静态检查
cd backend_api_python && pytest tests/        # 后端 pytest（从 tests 目录结构与 pytest 用法推导）
```

说明：后端命令在仓库配置中未显式写入脚本文件，但测试目录与 `pytest` 用法完整，且注释中出现 `pytest ... -m integration` 示例（`backend_api_python/tests/test_ibkr_client.py`）。

## 测试文件组织

**后端：**
- 主测试目录：`backend_api_python/tests/`
- 分层子目录：`backend_api_python/tests/live_trading/usmart/`
- 命名规范：`test_*.py`
- 当前扫描到：73 个 Python 测试文件（基于 `backend_api_python/tests/**/test_*.py` 扫描结果）

**前端：**
- 测试目录：`quantdinger_vue/tests/unit/`
- 命名规范：`*.spec.js`
- 当前扫描到：2 个单测文件（`frnt-01-forex-ibkr-options.spec.js`、`frnt-02-wizard-forex-market.spec.js`）

## 测试结构模式

**后端常见结构：**
```python
import pytest
from unittest.mock import MagicMock, patch

class TestHandleFillDB:
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_full_fill_flow(self, mock_sent):
        ...
```

证据路径：
- `backend_api_python/tests/test_ibkr_order_callback.py`
- `backend_api_python/tests/test_ibkr_client.py`

**前端常见结构：**
```javascript
describe('FRNT-02 ...', () => {
  beforeEach(() => { ... })
  it('shallow-mounts TradingAssistant ...', async () => {
    const wrapper = shallowMount(...)
    expect(wrapper.vm.isForexMarket).toBe(true)
  })
})
```

证据路径：
- `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`

## Mock 与依赖隔离模式

**后端：**
- 大量使用 `patch("app....")` 隔离数据库、网络和交易通道。
- 通过工厂函数构建 mock client/trade，统一状态初始化（`_make_client`、`_make_trade`）。
- `conftest.py` 中使用 `autouse=True` fixture 自动清理全局状态，避免测试污染。

证据路径：
- `backend_api_python/tests/conftest.py`
- `backend_api_python/tests/test_ibkr_order_callback.py`
- `backend_api_python/tests/test_ibkr_client.py`

**前端：**
- 使用 `jest.mock('@/api/...')` 隔离 API 调用。
- 使用 `stubs` 屏蔽大量 Ant Design Vue 组件，降低渲染复杂度。

证据路径：
- `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`

## Fixture 与测试数据模式

**后端：**
- 全局 fixtures：`backend_api_python/tests/conftest.py`
- 领域 mock 工具：`backend_api_python/tests/helpers/ibkr_mocks.py`
- 典型策略：通过 helper 统一构造 DB 上下文与交易对象，再在单测覆盖分支条件。

**前端：**
- 通过本地函数 `createFormMock` 构建表单 mock，按用例设置 `wrapper.setData(...)` 驱动状态机。

证据路径：
- `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`

## 覆盖率现状

**自动化覆盖率配置：**
- 未检测到后端覆盖率配置（无 `pytest-cov` 配置文件、无 `.coveragerc`、CI 未执行 coverage）。
- 前端未检测到覆盖率脚本（`quantdinger_vue/package.json` 仅有 `test:unit`，无 `test:coverage`）。

**CI 覆盖现状：**
- `.github/workflows/basic-ci.yml` 当前执行：
  - 后端：语法检查 + import 检查
  - 前端：依赖安装 + `npm run lint:nofix`
- 该 CI 未执行后端 pytest、未执行前端 jest、未产出任何 coverage 指标。

## 已覆盖的测试类型

**后端：**
- 单元测试：核心交易逻辑、路由、任务注册、数据处理模块（示例：`test_signal_executor.py`、`test_tasks_registry.py`、`test_universe_routes.py`）。
- 集成/场景测试：存在 `@pytest.mark.integration`、`test_forex_ibkr_e2e.py`、`test_strategy_http_e2e.py` 等端到端倾向用例。
- 参数化测试：`@pytest.mark.parametrize` 广泛使用（如 `backend_api_python/tests/test_ibkr_symbols.py`、`test_ibkr_client.py`）。

**前端：**
- 组件行为验证与源码断言（`frnt-01` 直接读取 `.vue` 文件断言文本；`frnt-02` 通过 shallowMount 断言计算属性和 HTML）。

## 主要测试缺口（潜在风险）

**缺口 1：CI 未执行测试**
- 现状：`.github/workflows/basic-ci.yml` 无 pytest/jest 步骤。
- 风险：合并前仅做语法与 lint，功能回归无法被流水线拦截。
- 优先级：高。

**缺口 2：覆盖率不可观测**
- 现状：无统一覆盖率命令与阈值。
- 风险：难以评估关键模块（交易路由、执行器、前端关键页面）是否得到充分回归保护。
- 优先级：高。

**缺口 3：前端测试样本过少**
- 现状：`quantdinger_vue/tests/unit/` 仅 2 个 `*.spec.js` 文件，但 `quantdinger_vue/src/` 有大量页面与组件（如 `src/views/`、`src/components/`）。
- 风险：UI 与业务交互改动的回归保护不足。
- 优先级：高。

**缺口 4：超大模块回归成本高**
- 现状：`backend_api_python/app/services/live_trading/ibkr_trading/client.py` 与 `quantdinger_vue/src/views/trading-assistant/index.vue` 体量大、分支多。
- 风险：单点改动引入旁路回归，现有测试难覆盖全部分支组合。
- 优先级：中高。

## 建议的最小增量改进路径

1. 在 `.github/workflows/basic-ci.yml` 增加后端 `pytest tests/` 与前端 `npm run test:unit`。
2. 为后端补充 `pytest-cov` 并产出 `xml`/终端报告；为前端补充 Jest 覆盖率脚本。
3. 先围绕高风险模块补测试：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`quantdinger_vue/src/views/trading-assistant/index.vue`。
4. 为 marker（`Forex`、`ForexRTH`、`integration`）定义分层执行策略（快速集 vs 全量集），提升日常反馈速度。

---

*Testing analysis: 2026-04-22*
# 测试模式与覆盖现状（Quality Focus）

**分析日期：** 2026-04-22

## 测试框架

**后端（Python）：**
- Runner：`pytest`（大量 `import pytest` 与 `@pytest.mark` 证据位于 `backend_api_python/tests/`，如 `backend_api_python/tests/test_ibkr_client.py`）。
- 共享配置：`backend_api_python/tests/conftest.py`（定义 `pytest_configure` marker 与通用 fixture）。
- Mock 工具：`unittest.mock`（`MagicMock`/`patch` 在 `backend_api_python/tests/test_ibkr_order_callback.py`、`backend_api_python/tests/test_ibkr_client.py` 中高频使用）。

**前端（Vue 2）：**
- Runner：Jest（`quantdinger_vue/jest.config.js`）。
- 组件测试：`@vue/test-utils`（`shallowMount` 用于组件挂载，见 `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。
- 断言：Jest `expect(...)`（见 `quantdinger_vue/tests/unit/*.spec.js`）。

## 运行命令（当前仓库可见）

```bash
cd quantdinger_vue && npm run test:unit      # 前端单元测试（package.json 已定义）
cd quantdinger_vue && npm run lint:nofix     # 前端静态检查
cd backend_api_python && pytest tests/        # 后端 pytest（从 tests 目录结构与 pytest 用法推导）
```

说明：后端命令在仓库配置中未显式写入脚本文件，但测试目录与 `pytest` 用法完整，且注释中出现 `pytest ... -m integration` 示例（`backend_api_python/tests/test_ibkr_client.py`）。

## 测试文件组织

**后端：**
- 主测试目录：`backend_api_python/tests/`
- 分层子目录：`backend_api_python/tests/live_trading/usmart/`
- 命名规范：`test_*.py`
- 当前扫描到：73 个 Python 测试文件（基于 `backend_api_python/tests/**/test_*.py` 扫描结果）

**前端：**
- 测试目录：`quantdinger_vue/tests/unit/`
- 命名规范：`*.spec.js`
- 当前扫描到：2 个单测文件（`frnt-01-forex-ibkr-options.spec.js`、`frnt-02-wizard-forex-market.spec.js`）

## 测试结构模式

**后端常见结构：**
```python
import pytest
from unittest.mock import MagicMock, patch

class TestHandleFillDB:
    @patch("app.services.live_trading.records.mark_order_sent")
    def test_full_fill_flow(self, mock_sent):
        ...
```

证据路径：
- `backend_api_python/tests/test_ibkr_order_callback.py`
- `backend_api_python/tests/test_ibkr_client.py`

**前端常见结构：**
```javascript
describe('FRNT-02 ...', () => {
  beforeEach(() => { ... })
  it('shallow-mounts TradingAssistant ...', async () => {
    const wrapper = shallowMount(...)
    expect(wrapper.vm.isForexMarket).toBe(true)
  })
})
```

证据路径：
- `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`

## Mock 与依赖隔离模式

**后端：**
- 大量使用 `patch("app....")` 隔离数据库、网络和交易通道。
- 通过工厂函数构建 mock client/trade，统一状态初始化（`_make_client`、`_make_trade`）。
- `conftest.py` 中使用 `autouse=True` fixture 自动清理全局状态，避免测试污染。

证据路径：
- `backend_api_python/tests/conftest.py`
- `backend_api_python/tests/test_ibkr_order_callback.py`
- `backend_api_python/tests/test_ibkr_client.py`

**前端：**
- 使用 `jest.mock('@/api/...')` 隔离 API 调用。
- 使用 `stubs` 屏蔽大量 Ant Design Vue 组件，降低渲染复杂度。

证据路径：
- `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`

## Fixture 与测试数据模式

**后端：**
- 全局 fixtures：`backend_api_python/tests/conftest.py`
- 领域 mock 工具：`backend_api_python/tests/helpers/ibkr_mocks.py`
- 典型策略：通过 helper 统一构造 DB 上下文与交易对象，再在单测覆盖分支条件。

**前端：**
- 通过本地函数 `createFormMock` 构建表单 mock，按用例设置 `wrapper.setData(...)` 驱动状态机。

证据路径：
- `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`

## 覆盖率现状

**自动化覆盖率配置：**
- 未检测到后端覆盖率配置（无 `pytest-cov` 配置文件、无 `.coveragerc`、CI 未执行 coverage）。
- 前端未检测到覆盖率脚本（`quantdinger_vue/package.json` 仅有 `test:unit`，无 `test:coverage`）。

**CI 覆盖现状：**
- `.github/workflows/basic-ci.yml` 当前执行：
  - 后端：语法检查 + import 检查
  - 前端：依赖安装 + `npm run lint:nofix`
- 该 CI 未执行后端 pytest、未执行前端 jest、未产出任何 coverage 指标。

## 已覆盖的测试类型

**后端：**
- 单元测试：核心交易逻辑、路由、任务注册、数据处理模块（示例：`test_signal_executor.py`、`test_tasks_registry.py`、`test_universe_routes.py`）。
- 集成/场景测试：存在 `@pytest.mark.integration`、`test_forex_ibkr_e2e.py`、`test_strategy_http_e2e.py` 等端到端倾向用例。
- 参数化测试：`@pytest.mark.parametrize` 广泛使用（如 `backend_api_python/tests/test_ibkr_symbols.py`、`test_ibkr_client.py`）。

**前端：**
- 组件行为验证与源码断言（`frnt-01` 直接读取 `.vue` 文件断言文本；`frnt-02` 通过 shallowMount 断言计算属性和 HTML）。

## 主要测试缺口（潜在风险）

**缺口 1：CI 未执行测试**
- 现状：`.github/workflows/basic-ci.yml` 无 pytest/jest 步骤。
- 风险：合并前仅做语法与 lint，功能回归无法被流水线拦截。
- 优先级：高。

**缺口 2：覆盖率不可观测**
- 现状：无统一覆盖率命令与阈值。
- 风险：难以评估关键模块（交易路由、执行器、前端关键页面）是否得到充分回归保护。
- 优先级：高。

**缺口 3：前端测试样本过少**
- 现状：`quantdinger_vue/tests/unit/` 仅 2 个 `*.spec.js` 文件，但 `quantdinger_vue/src/` 有大量页面与组件（如 `src/views/`、`src/components/`）。
- 风险：UI 与业务交互改动的回归保护不足。
- 优先级：高。

**缺口 4：超大模块回归成本高**
- 现状：`backend_api_python/app/services/live_trading/ibkr_trading/client.py` 与 `quantdinger_vue/src/views/trading-assistant/index.vue` 体量大、分支多。
- 风险：单点改动引入旁路回归，现有测试难覆盖全部分支组合。
- 优先级：中高。

## 建议的最小增量改进路径

1. 在 `.github/workflows/basic-ci.yml` 增加后端 `pytest tests/` 与前端 `npm run test:unit`。
2. 为后端补充 `pytest-cov` 并产出 `xml`/终端报告；为前端补充 Jest 覆盖率脚本。
3. 先围绕高风险模块补测试：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`quantdinger_vue/src/views/trading-assistant/index.vue`。
4. 为 marker（`Forex`、`ForexRTH`、`integration`）定义分层执行策略（快速集 vs 全量集），提升日常反馈速度。

---

*Testing analysis: 2026-04-22*
