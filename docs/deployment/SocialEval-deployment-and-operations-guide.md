# 自主知识创新法学评价系统部署与运维说明

**版本**：2026-04-16  
**适用范围**：单机 MVP 生产部署、容器化部署、宿主机 `systemd` 部署

> **现行容器部署说明（2026-07-24）**：当前 `docker-compose.prod.yml`
> 已切换为 Caddy 单一公网入口、独立 `migrate` 门禁和
> `.env.production`。部署编辑辅助预审系统时，以
> [`docs/editorial/deployment-single-host-docker.md`](../editorial/deployment-single-host-docker.md)
> 为准。本文件后续章节保留旧版 Nginx/systemd 方案，仅作为历史运维参考。

---

## 1. 当前推荐部署形态

当前仓库已经具备单机 MVP 生产部署骨架，推荐拓扑为：

- `Caddy`
- `FastAPI`
- `Celery Worker`
- `PostgreSQL`
- `Redis`
- `SMTP`
- 独立数据盘绑定挂载

配套上线能力已经覆盖：

- 生产环境变量校验与 Session/CORS 安全配置
- API / Worker Docker 镜像与 `docker-compose.prod.yml`
- `systemd` 服务单元
- SMTP 邮件发送
- 分块上传、容量与文件结构校验
- `/api/health/live`、`/api/health/ready` 和管理员运行状态接口
- JSON 结构化日志
- GitHub Actions CI
- 端到端 launch smoke test

云资源规格建议见：`docs/architecture/SocialEval-mvp-cloud-sizing.md`

若当前处于“先本地演示、后解决平台公网入口”的阶段，另见：

- `docs/deployment/local-demo-guide.md`

---

## 2. 仓库内现成部署文件

- API 镜像：`Dockerfile.api`
- 前端镜像：`src/web/Dockerfile`
- 生产编排：`docker-compose.prod.yml`
- Caddy 配置：`deploy/Caddyfile`
- API 服务单元：`deploy/systemd/socialeval-api.service`
- Worker 服务单元：`deploy/systemd/socialeval-worker.service`
- 生产环境变量示例：`docs/deployment/production-env.example.md`
- 上线清单与回滚计划：`docs/deployment/launch-checklist.md`

---

## 3. 上线前准备

### 3.1 基础设施

- 准备 `Ubuntu 22.04 LTS` 或同等级 Linux 主机
- 准备域名，例如 `app.socialeval.example`
- 配置 DNS A/AAAA 记录指向应用入口
- 申请 TLS 证书并规划 `80/443`
- 为 PostgreSQL、Redis、SMTP 准备网络访问策略

### 3.2 必须准备的密钥 / 凭据

- `SECRET_KEY`
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY`
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD`
- 数据库与 Redis 连接串

### 3.3 环境变量文件

以 `docs/deployment/production-env.example.md` 为基线填写正式配置，至少保证：

- `APP_ENV=production`
- `ALLOWED_ORIGINS` 为真实前端来源
- `SESSION_HTTPS_ONLY=true`
- `PUBLIC_BASE_URL` 指向用户访问地址

说明：

- 前端未显式设置 `VITE_API_BASE` 时，会优先走同源 `/api`
- 当前单机方案将 `/app/data` 绑定到独立数据盘的
  `${SOCIALEVAL_DATA_ROOT}/app`。
- 对象存储尚未作为应用主存储交付，只用于 Restic 客户端加密备份。

---

## 4. 容器化单机部署

### 4.1 准备 `.env`

```bash
cp .env.example .env
```

再按生产值修改 `.env`。

### 4.2 校验编排文件

```bash
docker compose -f docker-compose.prod.yml config
```

若宿主机没有 `docker compose` 插件，可改用：

```bash
docker-compose -f docker-compose.prod.yml config
```

### 4.3 构建镜像

```bash
docker compose -f docker-compose.prod.yml build api worker frontend
```

当前 `Dockerfile.api` 直接基于 `python:3.10` 运行时镜像，已经包含 PDF 导出所需的 Cairo / Pango 相关运行时库，因此不再依赖上线时额外 `apt-get install`。

### 4.4 启动依赖服务与迁移

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres redis
docker compose --env-file .env.production -f docker-compose.prod.yml up migrate
```

### 4.5 启动应用

第一次启动前先创建绑定挂载目录，并按镜像内固定用户设置权限：

```bash
sudo env SOCIALEVAL_DATA_ROOT=/srv/socialeval \
  ./deploy/scripts/prepare_data_dirs.sh
```

脚本只接受 `/srv` 下的专用子目录，避免误改宽泛路径。若升级基础镜像后改变了
PostgreSQL 或 Redis 的容器用户编号，须先复核脚本中的 UID/GID。

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

### 4.6 默认流量路径

- `/api/` -> `api:8000`
- `/` -> `frontend:80`

对外入口统一由 `proxy`（Caddy）暴露。

说明：

- `api` 与 `worker` 通过独立数据盘上的共享目录读写上传文件和导出产物。

---

## 5. 宿主机 + systemd 部署

适用于：

- PostgreSQL / Redis 由云服务提供
- 或希望应用直接运行在宿主机 Python 环境中

### 5.1 建议目录

- 代码：`/opt/socialeval`
- 环境变量：`/etc/socialeval/socialeval.env`
- systemd 运行用户：`socialeval`

### 5.2 宿主机准备

```bash
sudo useradd --system --home /opt/socialeval --shell /usr/sbin/nologin socialeval
sudo mkdir -p /etc/socialeval
sudo chown -R socialeval:socialeval /opt/socialeval /etc/socialeval
```

将仓库代码部署到 `/opt/socialeval`，并写入 `/etc/socialeval/socialeval.env`。

### 5.3 服务文件

复制：

- `deploy/systemd/socialeval-api.service`
- `deploy/systemd/socialeval-worker.service`

到 `/etc/systemd/system/`。

### 5.4 启动命令

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now socialeval-api
sudo systemctl enable --now socialeval-worker
```

如需查看运行状态：

```bash
sudo systemctl status socialeval-api
sudo journalctl -u socialeval-api -f
sudo journalctl -u socialeval-worker -f
```

---

## 6. Nginx 与 TLS

仓库已提供模板：

- `deploy/nginx/socialeval.conf`

该模板默认：

- 监听 `80`
- 将 `/api/` 代理到 API
- 将 `/` 代理到前端容器
- 设置常见反代头

正式生产应补齐：

- `443` 与证书续期
- HSTS
- 访问日志与错误日志落盘
- `client_max_body_size`
- 仅对公网暴露 `80/443`

---

## 7. 首个管理员初始化

当前仓库已支持“管理员邀请用户 -> 用户激活账号”的正式流程，但**首个管理员账号**仍需通过一次性种子方式创建。

推荐做法：

1. 先完成数据库迁移
2. 在生产环境中执行一次性脚本创建 `admin`
3. 首个管理员登录后，通过 `/api/users/invitations` 邀请其他角色账号

在应用容器中运行交互式初始化脚本，密码不会出现在命令历史或日志中：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  run --rm api python scripts/create_initial_admin.py \
  --email admin@example.com --display-name "系统管理员"
```

执行后必须：

- 立即登录并绑定双因素认证
- 将一次性恢复码离线保存在受控位置
- 用邀请流程创建其他账户，不直接写数据库

如果管理员同时丢失认证器和恢复码，应在受控运维终端执行：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml \
  run --rm api python scripts/reset_admin_mfa.py --email admin@example.com
```

该操作要求再次输入目标邮箱确认，并会同时撤销该管理员的全部会话、API Key
和旧恢复码；下一次登录必须重新绑定双因素认证。执行记录会写入审计日志。

---

## 8. 健康检查、日志与冒烟验证

### 8.1 健康检查

```bash
curl -fsS https://app.socialeval.example/api/health/live
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec -T api python -c \
  "import os,urllib.request; h=os.environ['ALLOWED_HOSTS'].split(',')[0]; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/health/ready',headers={'Host':h}))"
```

就绪检查会验证数据库、Redis 和上传目录；任一依赖失败时返回 503。Caddy
故意不向公网暴露 `/api/health/ready`，避免泄露内部依赖状态。

### 8.2 运维总览接口（管理员）

```bash
curl -fsS -H "X-API-Key: <admin-api-key>" \
  https://app.socialeval.example/api/health/operations
```

返回核心字段：

- `work_units`：处理单元状态计数
- `stalled_work_units`：超过停滞阈值的处理中单元
- `email_deliveries`：邮件投递状态计数
- `queue_depth`：Celery 队列深度

### 8.3 日志

API 与 Worker 启动后会输出 JSON 结构化日志，适合接入 Loki / ELK / 云日志服务。

### 8.4 最小冒烟路径

建议按以下顺序验证：

1. 管理员登录成功
2. 管理员创建 `submitter` / `editor` / `expert` 邀请
3. 受邀用户通过邮件中的 `/activate#token=...` 完成激活并返回登录页
4. 投稿人上传一篇样例论文，并手动点击“开始评测”
5. Worker 完成任务，论文状态变为 `completed`，投稿人可读取公开报告
6. 若稿件被预检拒稿，投稿人界面会显示“需重新上传”及重传提示，而不是伪造 `0` 分报告
7. 编辑可读取内部报告与复核队列，并完成专家分配
8. 专家登录后可在网页端打开分配到的任务，逐维度填写专家评分与修改理由并提交复核
9. 确认稿件和报告写入独立数据盘，Restic 能把加密备份写入私有存储桶
10. 若启用 SMTP，确认邀请/分配邮件成功发出

回归基线可参考自动化测试：`tests/integration/test_launch_smoke.py`

---

## 9. 备份、监控与回滚

上线前至少准备：

- PostgreSQL 迁移前快照 / 逻辑备份
- Redis 持久化策略确认
- Restic 私有存储桶的权限、版本控制与生命周期策略
- 应用日志保留周期

仓库已提供 `deploy/scripts/backup.sh`、每日备份定时器和
`deploy/scripts/healthcheck.sh`。备份组合使用 PostgreSQL 自定义格式逻辑备份、
独立数据盘文件和 Restic 客户端加密异机备份；Redis 不作为权威数据源。正式
恢复前必须停止全部写入入口，并先在临时数据库和临时目录演练。

恢复实操、前置条件、校验与回滚注意事项见：

- `docs/deployment/backup-and-recovery-runbook.md`

建议重点监控：

- 公网 `/api/health/live` 与容器内 `/api/health/ready` 状态
- `/api/admin/operations/overview` 中 `recovering`、`recent_failures`、`pending_reviews` 变化
- API 5xx 比例
- Celery 队列堆积
- PostgreSQL 连接数 / 磁盘空间
- Redis 内存占用
- SMTP 发送失败率

可使用仓库脚本做单机告警判断（超阈值返回非 0）：

```bash
uv run python scripts/ops_monitor.py \
  --endpoint https://app.socialeval.example/api/admin/operations/overview \
  --api-key "<admin-api-key>" \
  --max-recovering 0 \
  --max-recent-failures 0 \
  --max-pending-reviews 10
```

回滚触发条件与步骤见：`docs/deployment/launch-checklist.md`

---

## 10. 相关文档

- `docs/deployment/production-env.example.md`
- `docs/deployment/launch-checklist.md`
- `docs/deployment/backup-and-recovery-runbook.md`
- `docs/architecture/SocialEval-mvp-cloud-sizing.md`
