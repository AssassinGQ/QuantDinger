# 代码规范（Quality Focus）

**分析日期：** 2026-04-22

## 命名模式

**文件命名：**
- Python 测试文件使用 `test_*.py`，集中在 `backend_api_python/tests/`（示例：`backend_api_python/tests/test_ibkr_client.py`、`backend_api_python/tests/live_trading/usmart/test_usmart_client.py`）。
- Python 模块多使用 `snake_case.py`（示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/app/utils/logger.py`）。
- Vue 单文件组件使用 `PascalCase.vue` 与 `index.vue` 混合（示例：`quantdinger_vue/src/layouts/BasicLayout.vue`、`quantdinger_vue/src/views/trading-assistant/index.vue`）。
- 前端单测文件使用业务前缀 + `.spec.js`（示例：`quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

**函数命名：**
- Python 函数/方法主要采用 `snake_case`（示例：`parse_ibkr_mode`、`get_status`、`_compute_ibkr_trade_stats` 位于 `backend_api_python/app/routes/ibkr.py`）。
- Vue/JS 方法与变量采用 `camelCase`（示例：`ignoreResizeObserverError` 位于 `quantdinger_vue/src/main.js`；测试中的 `createFormMock` 位于 `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

**变量命名：**
- Python 局部变量以语义化 `snake_case` 为主（示例：`pending_order_id`、`strategy_id`，见 `backend_api_python/tests/test_ibkr_order_callback.py`）。
- JS 变量使用 `camelCase`，常量使用全大写（示例：`IS_PROD`、`IS_PREVIEW` 位于 `quantdinger_vue/babel.config.js`）。

**类型与数据结构命名：**
- Python dataclass 使用 `PascalCase`（示例：`IBKRConfig`、`IBKROrderContext`，位于 `backend_api_python/app/services/live_trading/ibkr_trading/client.py`）。
- Flask Blueprint 对象命名使用业务缩写（示例：`ibkr_bp`，位于 `backend_api_python/app/routes/ibkr.py`）。

## 代码风格

**格式化：**
- 前端存在 ESLint + Stylelint 的显式规则；`package.json` 中提供 `lint`、`lint:nofix`、`lint:js`、`lint:css`（`quantdinger_vue/package.json`）。
- ESLint 关键风格约束：单引号、无分号、关闭 `indent` 规则（`quantdinger_vue/.eslintrc.js`）。
- Stylelint 关键约束：单引号、最大嵌套层级 4、属性顺序规则（`quantdinger_vue/.stylelintrc.js`）。
- 后端未检测到 `pyproject.toml`、`setup.cfg`、`tox.ini`、`ruff.toml`；当前未发现统一格式化工具配置文件（仓库扫描结果）。

**静态检查：**
- 前端通过 `npm run lint:nofix` 执行 ESLint 检查（`quantdinger_vue/package.json`、`.github/workflows/basic-ci.yml`）。
- 后端 CI 当前执行语法编译与导入校验，不执行 Python lint（`python -m py_compile`、`python -m compileall`，见 `.github/workflows/basic-ci.yml`）。
- 代码中存在 `# pylint: disable=...` 注释（示例：`backend_api_python/app/services/live_trading/ef_trading/client.py`、`backend_api_python/tests/test_backtest_correctness_phase21.py`），说明团队有局部 pylint 约定但缺少仓库级统一配置。

## 导入组织

**Python 导入顺序（观察到的主流模式）：**
1. 标准库（如 `json`、`os`、`threading`），示例：`backend_api_python/app/services/live_trading/ibkr_trading/client.py`
2. 第三方库（如 `flask`、`pytest`），示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/tests/test_ibkr_order_callback.py`
3. 项目内模块 `from app...` 或 `from tests...`，示例：`backend_api_python/tests/conftest.py`

**前端导入顺序（观察到的主流模式）：**
1. polyfill/运行时（`core-js`、`regenerator-runtime`），见 `quantdinger_vue/src/main.js`
2. 框架与三方依赖（`vue`、`@ant-design-vue/*`）
3. 本地模块（`./router`、`./store/`、`./utils/*`）

**路径别名：**
- 前端测试与业务代码普遍使用 `@/` 指向 `src`（`quantdinger_vue/jest.config.js` 中 `moduleNameMapper` 配置，测试示例见 `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

## 错误处理规范

**后端模式：**
- 路由层广泛采用 `try/except Exception as e` 并返回 JSON 错误（示例：`backend_api_python/app/routes/ibkr.py` 中 `get_status`、`connect`、`place_order`）。
- 业务层存在“吞错并记录日志”的防御式处理（示例：`backend_api_python/app/services/live_trading/ibkr_trading/client.py` 中多处 `logger.warning` / `logger.error`）。

**前端模式：**
- 当前抽样测试重心在“业务逻辑与模板行为”，未见统一错误边界约定文档（示例：`quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js`）。

## 日志规范

**框架：**
- 后端使用 Python `logging` + `RotatingFileHandler`，日志文件落地 `logs/app.log`（`backend_api_python/app/utils/logger.py`）。

**记录模式：**
- 服务与路由内统一通过 `get_logger(__name__)` 获取 logger（示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`）。
- 失败分级以 `warning`/`error` 为主，关键异常可带 `exc_info=True`（示例：`ibkr_dashboard` 尾部错误处理，`backend_api_python/app/routes/ibkr.py`）。

## 注释与文档字符串

**何时注释：**
- 后端广泛使用模块级 docstring 与函数 docstring 说明意图（示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/tests/test_ibkr_client.py`）。
- 前端测试文件使用头部块注释描述测试范围（示例：`quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

**注释语言：**
- 中英混合，中文业务语义 + 英文技术描述并存（示例：`backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`quantdinger_vue/src/views/trading-assistant/index.vue`）。

## 函数设计

**规模特征：**
- 存在超大函数/方法与超大文件（如 `backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`quantdinger_vue/src/views/trading-assistant/index.vue`），可读性依赖内部注释与分区注释。

**参数与返回：**
- 路由层函数通常返回 `jsonify({...})` + HTTP 状态码（`backend_api_python/app/routes/ibkr.py`）。
- 测试辅助函数使用工厂模式集中构建 mock（示例：`_make_client`、`_make_trade`，`backend_api_python/tests/test_ibkr_order_callback.py`）。

## 模块设计

**导出模式：**
- Python 以显式导入为主，`__init__.py` 主要用于包声明与局部导出（示例：`backend_api_python/app/services/live_trading/ibkr_trading/__init__.py`）。
- Vue 模块通过默认导出组件与入口挂载（示例：`quantdinger_vue/src/main.js`）。

**分层边界：**
- 后端采用 `routes -> services -> utils/data access` 的实用分层（证据路径：`backend_api_python/app/routes/`、`backend_api_python/app/services/`、`backend_api_python/app/utils/`）。

## 当前规范缺口（潜在风险）

**Python 规范一致性缺口：**
- 问题：缺少仓库级 Python lint/format 配置文件（未检测到 `pyproject.toml` / `setup.cfg` / `tox.ini` / `ruff.toml`）。
- 影响：跨模块风格漂移难以及时发现，pylint 规则靠文件内局部 `disable` 维持。
- 建议：在 `backend_api_python/` 增补统一配置并在 CI 显式执行。

**CI 质量门禁缺口：**
- 问题：当前 CI 对后端只做语法和导入检查，不跑 pytest，不产出覆盖率（`.github/workflows/basic-ci.yml`）。
- 影响：回归风险在合并前无法自动暴露。
- 建议：在 CI 增加 `pytest`（至少核心模块 smoke）与覆盖率报告步骤。

**超大文件维护缺口：**
- 问题：`backend_api_python/app/services/live_trading/ibkr_trading/client.py` 与 `quantdinger_vue/src/views/trading-assistant/index.vue` 体量显著偏大。
- 影响：审查成本高、单点修改引发连锁回归概率上升。
- 建议：拆分子模块（订单路由、事件处理、UI 子组件）并补充对应单测。

---

*Convention analysis: 2026-04-22*
# 代码规范（Quality Focus）

**分析日期：** 2026-04-22

## 命名模式

**文件命名：**
- Python 测试文件使用 `test_*.py`，集中在 `backend_api_python/tests/`（示例：`backend_api_python/tests/test_ibkr_client.py`、`backend_api_python/tests/live_trading/usmart/test_usmart_client.py`）。
- Python 模块多使用 `snake_case.py`（示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/app/utils/logger.py`）。
- Vue 单文件组件使用 `PascalCase.vue` 与 `index.vue` 混合（示例：`quantdinger_vue/src/layouts/BasicLayout.vue`、`quantdinger_vue/src/views/trading-assistant/index.vue`）。
- 前端单测文件使用业务前缀 + `.spec.js`（示例：`quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

**函数命名：**
- Python 函数/方法主要采用 `snake_case`（示例：`parse_ibkr_mode`、`get_status`、`_compute_ibkr_trade_stats` 位于 `backend_api_python/app/routes/ibkr.py`）。
- Vue/JS 方法与变量采用 `camelCase`（示例：`ignoreResizeObserverError` 位于 `quantdinger_vue/src/main.js`；测试中的 `createFormMock` 位于 `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

**变量命名：**
- Python 局部变量以语义化 `snake_case` 为主（示例：`pending_order_id`、`strategy_id`，见 `backend_api_python/tests/test_ibkr_order_callback.py`）。
- JS 变量使用 `camelCase`，常量使用全大写（示例：`IS_PROD`、`IS_PREVIEW` 位于 `quantdinger_vue/babel.config.js`）。

**类型与数据结构命名：**
- Python dataclass 使用 `PascalCase`（示例：`IBKRConfig`、`IBKROrderContext`，位于 `backend_api_python/app/services/live_trading/ibkr_trading/client.py`）。
- Flask Blueprint 对象命名使用业务缩写（示例：`ibkr_bp`，位于 `backend_api_python/app/routes/ibkr.py`）。

## 代码风格

**格式化：**
- 前端存在 ESLint + Stylelint 的显式规则；`package.json` 中提供 `lint`、`lint:nofix`、`lint:js`、`lint:css`（`quantdinger_vue/package.json`）。
- ESLint 关键风格约束：单引号、无分号、关闭 `indent` 规则（`quantdinger_vue/.eslintrc.js`）。
- Stylelint 关键约束：单引号、最大嵌套层级 4、属性顺序规则（`quantdinger_vue/.stylelintrc.js`）。
- 后端未检测到 `pyproject.toml`、`setup.cfg`、`tox.ini`、`ruff.toml`；当前未发现统一格式化工具配置文件（仓库扫描结果）。

**静态检查：**
- 前端通过 `npm run lint:nofix` 执行 ESLint 检查（`quantdinger_vue/package.json`、`.github/workflows/basic-ci.yml`）。
- 后端 CI 当前执行语法编译与导入校验，不执行 Python lint（`python -m py_compile`、`python -m compileall`，见 `.github/workflows/basic-ci.yml`）。
- 代码中存在 `# pylint: disable=...` 注释（示例：`backend_api_python/app/services/live_trading/ef_trading/client.py`、`backend_api_python/tests/test_backtest_correctness_phase21.py`），说明团队有局部 pylint 约定但缺少仓库级统一配置。

## 导入组织

**Python 导入顺序（观察到的主流模式）：**
1. 标准库（如 `json`、`os`、`threading`），示例：`backend_api_python/app/services/live_trading/ibkr_trading/client.py`
2. 第三方库（如 `flask`、`pytest`），示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/tests/test_ibkr_order_callback.py`
3. 项目内模块 `from app...` 或 `from tests...`，示例：`backend_api_python/tests/conftest.py`

**前端导入顺序（观察到的主流模式）：**
1. polyfill/运行时（`core-js`、`regenerator-runtime`），见 `quantdinger_vue/src/main.js`
2. 框架与三方依赖（`vue`、`@ant-design-vue/*`）
3. 本地模块（`./router`、`./store/`、`./utils/*`）

**路径别名：**
- 前端测试与业务代码普遍使用 `@/` 指向 `src`（`quantdinger_vue/jest.config.js` 中 `moduleNameMapper` 配置，测试示例见 `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

## 错误处理规范

**后端模式：**
- 路由层广泛采用 `try/except Exception as e` 并返回 JSON 错误（示例：`backend_api_python/app/routes/ibkr.py` 中 `get_status`、`connect`、`place_order`）。
- 业务层存在“吞错并记录日志”的防御式处理（示例：`backend_api_python/app/services/live_trading/ibkr_trading/client.py` 中多处 `logger.warning` / `logger.error`）。

**前端模式：**
- 当前抽样测试重心在“业务逻辑与模板行为”，未见统一错误边界约定文档（示例：`quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js`）。

## 日志规范

**框架：**
- 后端使用 Python `logging` + `RotatingFileHandler`，日志文件落地 `logs/app.log`（`backend_api_python/app/utils/logger.py`）。

**记录模式：**
- 服务与路由内统一通过 `get_logger(__name__)` 获取 logger（示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/app/services/live_trading/ibkr_trading/client.py`）。
- 失败分级以 `warning`/`error` 为主，关键异常可带 `exc_info=True`（示例：`ibkr_dashboard` 尾部错误处理，`backend_api_python/app/routes/ibkr.py`）。

## 注释与文档字符串

**何时注释：**
- 后端广泛使用模块级 docstring 与函数 docstring 说明意图（示例：`backend_api_python/app/routes/ibkr.py`、`backend_api_python/tests/test_ibkr_client.py`）。
- 前端测试文件使用头部块注释描述测试范围（示例：`quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`）。

**注释语言：**
- 中英混合，中文业务语义 + 英文技术描述并存（示例：`backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`quantdinger_vue/src/views/trading-assistant/index.vue`）。

## 函数设计

**规模特征：**
- 存在超大函数/方法与超大文件（如 `backend_api_python/app/services/live_trading/ibkr_trading/client.py`、`quantdinger_vue/src/views/trading-assistant/index.vue`），可读性依赖内部注释与分区注释。

**参数与返回：**
- 路由层函数通常返回 `jsonify({...})` + HTTP 状态码（`backend_api_python/app/routes/ibkr.py`）。
- 测试辅助函数使用工厂模式集中构建 mock（示例：`_make_client`、`_make_trade`，`backend_api_python/tests/test_ibkr_order_callback.py`）。

## 模块设计

**导出模式：**
- Python 以显式导入为主，`__init__.py` 主要用于包声明与局部导出（示例：`backend_api_python/app/services/live_trading/ibkr_trading/__init__.py`）。
- Vue 模块通过默认导出组件与入口挂载（示例：`quantdinger_vue/src/main.js`）。

**分层边界：**
- 后端采用 `routes -> services -> utils/data access` 的实用分层（证据路径：`backend_api_python/app/routes/`、`backend_api_python/app/services/`、`backend_api_python/app/utils/`）。

## 当前规范缺口（潜在风险）

**Python 规范一致性缺口：**
- 问题：缺少仓库级 Python lint/format 配置文件（未检测到 `pyproject.toml` / `setup.cfg` / `tox.ini` / `ruff.toml`）。
- 影响：跨模块风格漂移难以及时发现，pylint 规则靠文件内局部 `disable` 维持。
- 建议：在 `backend_api_python/` 增补统一配置并在 CI 显式执行。

**CI 质量门禁缺口：**
- 问题：当前 CI 对后端只做语法和导入检查，不跑 pytest，不产出覆盖率（`.github/workflows/basic-ci.yml`）。
- 影响：回归风险在合并前无法自动暴露。
- 建议：在 CI 增加 `pytest`（至少核心模块 smoke）与覆盖率报告步骤。

**超大文件维护缺口：**
- 问题：`backend_api_python/app/services/live_trading/ibkr_trading/client.py` 与 `quantdinger_vue/src/views/trading-assistant/index.vue` 体量显著偏大。
- 影响：审查成本高、单点修改引发连锁回归概率上升。
- 建议：拆分子模块（订单路由、事件处理、UI 子组件）并补充对应单测。

---

*Convention analysis: 2026-04-22*
