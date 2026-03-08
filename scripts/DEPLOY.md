# QuantDinger 更新部署

按 QuantDinger 技能 [infrastructure.md](../../ai-coder/skills/skills/quantdinger-trading/references/infrastructure.md) 执行。

## 前置

- 已完成 `git push hgq main`（或 `git push origin main`）
- 本次变更：新增 usmart_trading 模块

## 步骤 1：WSL 推送

```bash
cd /home/hgq/workspace/aicoder/ws4/QuantDinger
git push hgq main
```

## 步骤 2：确定可用服务器地址

```bash
# 先 ping 确定可用地址
ping -c 1 -W 2 192.168.0.118 && echo "USE: 192.168.0.118" || \
ping -c 1 -W 2 hgq-nas && echo "USE: hgq-nas" || \
echo "BOTH UNREACHABLE - check network"
```

## 步骤 3：SSH 容器内拉取并编译前端

```bash
# 登录 SSH 容器（端口 322）
ssh -p 322 root@<确定的主机名或IP>

# 拉取代码
cd /home/workspace/ws/QuantDinger
git pull --rebase hgq main
# 或: git pull --rebase origin main

# 编译前端（若有前端变更）
cd quantdinger_vue
npm install --legacy-peer-deps   # 若依赖有变
npm run build

# 退出
exit
```

## 步骤 4：NAS 宿主机更新 Docker 容器

```bash
# 登录 NAS 宿主机
ssh admin@<确定的主机名或IP>

# 设置 docker 路径（必须！非交互 SSH 无 docker）
export PATH=/share/CACHEDEV1_DATA/.qpkg/container-station/bin:$PATH

# 进入 QuantDinger 目录
cd /share/Data2/ubuntu/ws/QuantDinger

# 更新后端
bash scripts/update-backend-in-docker.sh

# 更新前端（需要步骤 3 已生成 dist）
bash scripts/update-frontend-in-docker.sh

exit
```

## 验证

- 前端：http://<主机>:8888
- 后端：http://<主机>:35000/api/...
- 检查日志：`ssh admin@<主机> "tail -50 /share/Data2/ubuntu/quantdinger/backend_logs/app.log"`
