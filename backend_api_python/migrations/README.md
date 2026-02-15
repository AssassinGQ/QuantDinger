# 数据库迁移说明

## 增量执行迁移（Docker 部署的 Postgres）

已有库只需执行**增量脚本**，不要重新跑完整 `init.sql`。

### 方式一：docker exec + psql（推荐）

在**宿主机**项目根目录（含 `docker-compose.yml`）下执行：

```bash
# 进入 QuantDinger 目录
cd /path/to/QuantDinger

# 执行增量脚本（容器内 /migrations 已挂载为 backend_api_python/migrations）
docker exec -i quantdinger-db psql -U quantdinger -d quantdinger < backend_api_python/migrations/002_qd_kline_cache.sql
```

若数据库/用户不同，替换 `-U`、`-d` 与 compose 里一致即可，例如：

```bash
docker exec -i quantdinger-db psql -U 你的用户 -d 你的库名 < backend_api_python/migrations/002_qd_kline_cache.sql
```

### 方式二：先进入容器再执行

```bash
# 进入 postgres 容器
docker exec -it quantdinger-db sh

# 容器内执行（脚本在挂载的 /migrations 下）
psql -U quantdinger -d quantdinger -f /migrations/002_qd_kline_cache.sql

# 退出
exit
```

### 方式三：宿主机有 psql 客户端且端口已映射

```bash
cd /path/to/QuantDinger
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=quantdinger PGPASSWORD=quantdinger123 PGDATABASE=quantdinger
psql -f backend_api_python/migrations/002_qd_kline_cache.sql
```

### 验证

执行后检查表是否创建成功：

```bash
docker exec -it quantdinger-db psql -U quantdinger -d quantdinger -c "\dt qd_kline_cache"
```

应看到表 `qd_kline_cache`。

## 首次部署（全新库）

Postgres 容器首次启动时会自动执行 `docker-entrypoint-initdb.d/01-init.sql`（即 `init.sql`），无需手动跑增量脚本。

## 迁移文件约定

- `init.sql`：全量建表，仅用于新库初始化。
- `002_*.sql`：增量迁移，可对已有库重复执行（脚本内使用 IF NOT EXISTS）。
