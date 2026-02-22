# QuantDinger 更新部署

按 QuantDinger 技能 [infrastructure.md](../../ai-coder/skills/skills/quantdinger-trading/references/infrastructure.md) 执行。

## 前置

- 已完成 `git push hgq main`（或 `git push origin main`）
- 当前变更：后端 `send-test-notification` 接口 + 前端 `handleTestNotification` 真实调用

## 步骤 1：WSL 推送（已完成）

```bash
cd /home/hgq/workspace/aicoder/ws4/QuantDinger
git push hgq main
```

## 步骤 2：SSH 容器内拉取并编译前端

```bash
# 登录 SSH 容器
ssh -p 322 root@hgq-nas

# 拉取代码
cd /home/workspace/ws/QuantDinger
git pull --rebase hgq main
# 或: git pull --rebase origin main

# 编译前端（本次有前端变更）
cd quantdinger_vue
npm install --legacy-peer-deps   # 若依赖有变
npm run build

# 退出
exit
```

## 步骤 3：NAS 宿主机更新 Docker 容器

```bash
# 登录 NAS 宿主机
ssh admin@hgq-nas

# 设置 docker 路径（必须！非交互 SSH 无 docker）
export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:$PATH

# 进入 QuantDinger 目录（按实际路径调整）
cd /share/Data2/ubuntu/ws/QuantDinger

# 更新后端
bash scripts/update-backend-in-docker.sh

# 更新前端（需要步骤 2 已生成 dist）
bash scripts/update-frontend-in-docker.sh

exit
```

## 验证

- 前端：http://hgq-nas:8888 或 http://<局域网IP>:8888
- 个人中心 → 通知设置 → 勾选邮件、填写邮箱 → 点击「发送测试通知」
- 应能收到测试邮件
