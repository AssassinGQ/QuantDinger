# 代码库关注点（Concerns）

**分析日期：** 2026-04-22

## 技术债（Tech Debt）

**动态代码执行链路分叉（同域能力两套实现）:**
- Issue: 指标代码校验接口直接 `exec` 用户输入，而通用安全执行能力已经独立在 `safe_exec` 中，形成“同类需求、不同防护基线”的技术债。
- Files: `backend_api_python/app/routes/indicator.py`, `backend_api_python/app/utils/safe_exec.py`, `backend_api_python/app/services/indicator_params.py`, `backend_api_python/app/services/backtest.py`
- Impact: 安全策略和超时/资源限制难统一，后续修复容易出现漏改入口。
- Fix approach: 统一改为单一执行网关（预校验 + 安全执行），禁止路由层裸 `exec`。

**核心模块体量过大且职责混合:**
- Issue: 多个关键文件超过 1k 行，集成“参数解析、领域逻辑、异常恢复、外部适配、落库”多职责。
- Files: `backend_api_python/app/services/backtest.py` (3856 行), `backend_api_python/app/services/live_trading/ibkr_trading/client.py` (1784 行), `backend_api_python/app/routes/global_market.py` (1778 行), `backend_api_python/app/routes/settings.py` (1318 行), `backend_api_python/app/services/portfolio_monitor.py` (1284 行)
- Impact: 变更半径大、回归成本高，问题定位与代码评审效率持续下降。
- Fix approach: 先按边界拆分（路由层/编排层/适配层/存储层），再以模块级测试封装行为。

## 已知缺陷（Known Bugs）

**凭据接口与实现语义不一致（“vault”名义但实际明文）:**
- Symptoms: 凭据路由注释声明“no encryption/decryption”，并将 `api_key`/`secret_key`/`passphrase` 序列化后直接写入 `encrypted_config` 字段。
- Files: `backend_api_python/app/routes/credentials.py`
- Trigger: 调用 `/credentials/create` 创建任意交易所凭据时。
- Workaround: 仅在隔离环境使用；生产通过 DB 访问控制和最小权限兜底。

## 安全考量（Security Considerations）

**默认弱凭据和默认密钥仍可启动:**
- Risk: 存在 `SECRET_KEY` 默认值与 `ADMIN_PASSWORD` 默认值，若部署遗漏环境变量会引入可预测凭据。
- Files: `backend_api_python/app/config/settings.py`
- Current mitigation: 支持环境变量覆盖。
- Recommendations: 启动时检测默认值并拒绝启动；将安全基线纳入健康检查。

**交易所 API 凭据明文落库:**
- Risk: `encrypted_config` 字段实际存储明文 JSON，数据库泄露会直接暴露交易权限。
- Files: `backend_api_python/app/routes/credentials.py`
- Current mitigation: 仅展示 `api_key_hint`，但完整凭据仍可通过 `/get` 返回给已登录用户。
- Recommendations: 引入字段级加密（KMS/应用层密封）+ 访问审计 + 凭据轮换策略。

**用户代码执行面仍存在裸 `exec`:**
- Risk: 指标验证与部分策略编译流程直接执行动态代码，安全边界依赖调用方约束而非统一策略。
- Files: `backend_api_python/app/routes/indicator.py`, `backend_api_python/app/strategies/single_symbol_indicator.py`, `backend_api_python/app/strategies/cross_sectional_indicator.py`, `backend_api_python/app/services/backtest.py`
- Current mitigation: 存在 `validate_code_safety` / `safe_exec_code` 工具，但并非所有入口强制使用。
- Recommendations: 统一入口并强制执行 AST/黑名单校验、超时、资源限制与隔离执行。

## 性能瓶颈（Performance Bottlenecks）

**轮询驱动的后台执行模型易放大资源开销:**
- Problem: `PendingOrderWorker` 常驻线程 + 固定 sleep 轮询，结合交易执行线程与 DB 读写形成持续负载。
- Files: `backend_api_python/app/services/pending_order_worker.py`, `backend_api_python/app/services/live_trading/records.py`, `backend_api_python/app/services/live_trading/ibkr_trading/client.py`
- Cause: 以固定轮询替代事件驱动/消息队列，线程和查询频率与业务峰值解耦不足。
- Improvement path: 引入消息队列或通知机制，降低空轮询；增加队列积压、处理延迟和失败重试指标。

## 脆弱区域（Fragile Areas）

**IBKR 客户端异常处理过于宽泛:**
- Files: `backend_api_python/app/services/live_trading/ibkr_trading/client.py`
- Why fragile: 该文件存在大量 `except Exception`，部分分支直接返回 `False` 或降级，故障语义易被掩盖。
- Safe modification: 先分层定义异常类型（连接、鉴权、下单、回调），再逐步替换 broad catch。
- Test coverage: 有 `backend_api_python/tests/test_ibkr_client.py` 与 `backend_api_python/tests/test_ibkr_order_callback.py`，但并发重连/事件风暴场景证据不足。

**配置解析失败默认值兜底可能掩盖配置错误:**
- Files: `backend_api_python/app/utils/config_loader.py`
- Why fragile: 多处转换异常后返回 `0/False/{}`，部署误配置时服务可继续运行但行为偏离预期。
- Safe modification: 为关键配置增加强校验（必填 + 类型 + 取值范围）并在启动期失败快。
- Test coverage: 未发现针对“错误配置导致拒绝启动”的专门测试文件。

## 扩展性限制（Scaling Limits）

**线程并发与 DB 连接池以经验公式耦合:**
- Current capacity: 连接池默认 `max(40, STRATEGY_MAX_THREADS + 80)`，线程上限与池大小联动。
- Limit: 高并发下可能出现线程等待连接、外部 API 限速与重试叠加放大。
- Scaling path: 建立容量压测基线（线程/连接/QPS），拆分读写池并加入背压与熔断。

## 依赖风险（Dependencies at Risk）

**`psycopg2` 缺失直接降级为 PostgreSQL 不可用:**
- Risk: 运行环境依赖完整性不满足时，核心数据路径不可用。
- Impact: 涉及 `get_pg_connection` 的功能将报错或不可用。
- Migration plan: 在镜像构建与启动阶段加依赖自检，缺失即阻断发布。

## 缺失的关键能力（Missing Critical Features）

**安全配置启动闸门缺失:**
- Problem: 默认密钥、默认口令、宽 CORS 等风险配置仍允许服务启动。
- Blocks: 运维只能靠人工 checklist，无法在系统层“阻止不安全部署”。

**统一作业运行时可观测性不足:**
- Problem: 后台 worker 与交易执行缺少统一健康探针（队列积压、失败率、重试次数、死信量）。
- Blocks: 出现“服务在线但交易链路劣化”时，故障发现滞后。

## 测试覆盖缺口（Test Coverage Gaps）

**动态执行安全边界测试不足:**
- What's not tested: `verifyCode` 路由与策略编译路径的危险调用拦截、超时限制、资源限制一致性。
- Files: `backend_api_python/app/routes/indicator.py`, `backend_api_python/app/utils/safe_exec.py`, `backend_api_python/tests/test_indicator_group.py`
- Risk: 动态代码安全回归难以及时发现。
- Priority: High

**前端自动化测试覆盖面偏窄:**
- What's not tested: 前端代码文件约 159 个（排除 `node_modules/dist`），测试文件仅约 3 个，关键交易与配置页面缺少回归保护。
- Files: `quantdinger_vue/tests/unit/frnt-01-forex-ibkr-options.spec.js`, `quantdinger_vue/tests/unit/frnt-02-wizard-forex-market.spec.js`
- Risk: UI 交互和配置变更容易出现无感回归。
- Priority: High

---

*关注点审计：2026-04-22*
