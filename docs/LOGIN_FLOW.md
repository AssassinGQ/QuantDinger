# QuantDinger 登录流程说明

本文档描述从用户按下「登录」按钮到登录完成，系统需要执行的操作、网络请求和数据库访问。

---

## 一、登录页面加载时（进入登录页时）

用户尚未点击登录按钮，进入 `/#/user/login` 时：

| 步骤 | 操作 | 网络请求 | 数据库访问 |
|------|------|----------|------------|
| 1 | `Login.vue` 的 `created()` 钩子执行 | - | - |
| 2 | 调用 `loadSecurityConfig()` | **GET** `/api/auth/security-config` | 无（仅读环境变量） |
| 3 | 检查 URL 中是否有 OAuth 回调参数 `oauth_token` | 若有则走 OAuth 流程，可能调用 GET `/api/auth/info` | - |
| 4 | 若开启 Turnstile，用户需完成人机验证 | 浏览器 → Cloudflare Turnstile（前端完成，不经过后端） | - |

**`/api/auth/security-config` 响应内容**：`turnstile_enabled`、`turnstile_site_key`、`registration_enabled`、OAuth 开关等，供前端决定是否显示验证码、OAuth 按钮等。

---

## 二、密码登录：点击登录按钮后

### 2.1 前端流程

```
用户点击登录
    → handleLogin(e) 阻止默认提交
    → 校验 legalAgreed（用户协议勾选）
    → loginForm.validateFields(['username', 'password'])
    → Vuex: Login({ username, password, turnstile_token })
    → api/login.js: request.post('/api/auth/login', data)
```

### 2.2 后端处理：`POST /api/auth/login`

后端按顺序执行以下步骤：

| 步骤 | 操作 | 网络请求 | 数据库访问 |
|------|------|----------|------------|
| 1 | 解析请求体 `{ username, password, turnstile_token }` | - | - |
| 2 | 若开启 Turnstile：校验验证码 | **POST** `https://challenges.cloudflare.com/turnstile/v0/siteverify` | - |
| 3 | 风控检查：`check_login_allowed(username, ip)` | - | **SELECT** `qd_login_attempts`：查询 IP 和账号近期失败次数 |
| 4 | 认证用户 | - | 见下表 |
| 5 | 认证成功后：递增 `token_version`（踢出其他设备） | - | **UPDATE** `qd_users` SET `token_version = token_version + 1` |
| 6 | 生成 JWT Token（本地计算，无网络/DB） | - | - |
| 7 | 记录成功登录、清理失败计数、写安全日志 | - | **INSERT** `qd_login_attempts`（成功记录）<br>**DELETE** `qd_login_attempts`（清理 ip/account）<br>**INSERT** `qd_security_logs` |
| 8 | 返回 `{ token, userinfo }` | - | - |

**认证阶段（步骤 4）的数据库访问**：

| 认证模式 | 操作 | 数据库访问 |
|----------|------|------------|
| **多用户模式** | `user_service.authenticate()` | **SELECT** `qd_users`（按 username 或 email 查用户）<br>**UPDATE** `qd_users` SET `last_login_at = NOW()` |
| **单用户模式**（`SINGLE_USER_MODE=true`） | `authenticate_legacy()` | 无（仅比较 `ADMIN_USER` / `ADMIN_PASSWORD` 环境变量）<br>成功后仍会执行 `increment_token_version`，访问 `qd_users` |

**认证失败时**：

- **INSERT** `qd_login_attempts`（记录失败）
- **INSERT** `qd_security_logs`（安全事件）

---

## 三、登录成功后的前端处理

| 步骤 | 操作 | 网络请求 | 数据库访问 |
|------|------|----------|------------|
| 1 | Vuex 将 `token`、`userinfo`、`roles` 写入 store 和 localStorage | - | - |
| 2 | `dispatch('ResetRoutes')` 清空动态路由 | - | - |
| 3 | `router.push({ path: '/' })` 跳转到首页 | - | - |
| 4 | 路由守卫 `beforeEach`：若有 token 且 `roles` 不为空，则 `GenerateRoutes` 生成动态路由（本地） | - | - |
| 5 | 进入首页 | - | - |

说明：密码登录时，`userinfo` 已在 `/api/auth/login` 响应中返回，**不会**再发起 `GET /api/auth/info`。

---

## 四、邮箱验证码登录（login-code）

邮箱验证码登录走 `POST /api/auth/login-code`，与密码登录不同，但数据库与外部依赖类似，此处不再展开。

---

## 五、涉及的数据表汇总

| 表名 | 用途 |
|------|------|
| `qd_users` | 用户信息、`token_version`、`last_login_at` |
| `qd_login_attempts` | 登录尝试记录（防暴力破解） |
| `qd_security_logs` | 安全审计日志 |

---

## 六、涉及的外部服务

| 服务 | 用途 |
|------|------|
| Cloudflare Turnstile | 人机验证（可选） |
| 无 | 密码登录不依赖其他外部 API |

---

## 七、完整流程时序（密码登录）

```
[前端] 用户点击登录
    ↓
[前端] POST /api/auth/login { username, password, turnstile_token }
    ↓
[后端] 1. Turnstile 校验（若开启）→ POST Cloudflare
[后端] 2. 风控检查 → SELECT qd_login_attempts
[后端] 3. 认证 → SELECT qd_users / UPDATE last_login_at
[后端] 4. 递增 token_version → UPDATE qd_users
[后端] 5. 生成 JWT（本地）
[后端] 6. 记录成功、清理失败 → INSERT/DELETE qd_login_attempts, INSERT qd_security_logs
[后端] 7. 返回 { token, userinfo }
    ↓
[前端] 保存 token、userinfo、roles
[前端] ResetRoutes → router.push('/')
[前端] 路由守卫生成动态路由 → 进入首页
```

---

## 八、超时配置

- 登录相关接口超时：前端 90 秒（`LOGIN_TIMEOUT`）
- 全局请求超时：60 秒（`request.js`）
- 登录慢时可重点排查：Turnstile、数据库连接、`qd_users` / `qd_login_attempts` 查询性能

---

## 九、耗时日志（调试用）

后端为每个流程步骤打耗时日志，统一以 `[LOGIN_FLOW]` 开头，便于筛选：

```bash
grep '\[LOGIN_FLOW\]' app.log
```

**密码登录（/api/auth/login）** 步骤标签：
- `security_config`：GET security-config 接口耗时
- `turnstile`：Turnstile 校验耗时（含 Cloudflare 网络请求）
- `rate_limit_check`：风控检查耗时
- `authenticate`：认证耗时（含 DB 查询、密码校验）
- `increment_token_version`：递增 token 版本耗时
- `generate_token`：JWT 生成耗时
- `record_success`：记录成功登录耗时
- `success_total`：登录成功总耗时

**邮箱验证码登录（/api/auth/login-code）** 步骤标签：
- `turnstile` / `verify_code` / `auth_or_create_user` / `increment_token_version` / `success_total`
