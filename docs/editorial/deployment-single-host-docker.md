# Linux 单机 Docker 部署

## 决策

先在本地完成自动化和端到端测试，再把相同镜像部署到云端预发布环境。第一阶段使用
Docker Compose，不直接在宿主机安装 Python、Node、PostgreSQL 或 Redis，也不引入
Kubernetes。

## 服务

- `proxy`：Caddy，唯一公开 `80/443`；
- `frontend`：React 静态站点；
- `api`：FastAPI；
- `worker`：Celery；
- `postgres`：业务和审计数据；
- `redis`：任务队列。

PostgreSQL 和 Redis 不映射公网端口。稿件、报告、数据库、Redis 与 Caddy 状态均绑定
到 `SOCIALEVAL_DATA_ROOT` 指向的独立数据盘；备份由 Restic 加密后复制到私有交大云
对象存储。

## 发布顺序

1. 本地：单元测试、API 测试、前端测试和构建；
2. 云端预发布：迁移、健康检查、HTTPS、权限和备份恢复演练；
3. 试运行：只使用获授权稿件，候选建议保持受控展示；
4. 按编辑单元批准正式启用。

## 首次启动

```bash
cp .env.production.example .env.production
# 编辑 .env.production，设置域名、随机密码、SECRET_KEY 和获授权的模型凭据
docker compose --env-file .env.production -f docker-compose.prod.yml config
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

`migrate` 服务会先执行 `alembic upgrade head`，成功后 API 和 Worker 才启动。
迁移 `010` 会创建三个初始试运行编辑单元；迁移 `011` 增加模型集快照、形式检查、
两阶段决定与专家独立评阅字段；迁移 `012` 增加持久化处理单元、邮件发件箱和
验证签字记录。管理员随后在后台添加成员。

正式域名解析到云主机后，`APP_DOMAIN` 使用域名，Caddy 自动申请和续期证书。
只做内网预发布时可以临时使用 `APP_DOMAIN=:80`，此时应保持防火墙限制来源，且不能
用于真实稿件。

## 升级与回滚

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml build
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 api worker
```

发布前先记录当前 Git commit 和镜像摘要。代码回滚与数据库降级必须分开评估；不要在
包含真实投稿后自动运行 `alembic downgrade`。

升级到编辑报告 v4 后，先列出待升级投稿，再显式追加新版本。脚本只追加新快照，
不会覆盖历史报告；重复执行不会再次追加 v4：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec api \
  python scripts/upgrade_editorial_reports_v4.py
docker compose --env-file .env.production -f docker-compose.prod.yml exec api \
  python scripts/upgrade_editorial_reports_v4.py --execute
```

## 生产检查

- 使用强随机 `SECRET_KEY`，模型和邮件凭据仅通过环境注入；
- 独立生成 `FIELD_ENCRYPTION_KEY`，管理员强制启用 TOTP；
- 首次启动前运行 `deploy/scripts/prepare_data_dirs.sh`，确保数据库、队列和稿件
  目录可由各自容器用户写入；
- 设置 `APP_ENV=production`、HTTPS 的 `PUBLIC_BASE_URL`、准确的
  `ALLOWED_ORIGINS` 与 `ALLOWED_HOSTS`；生产配置缺失时 API 会拒绝启动；
- SMTP 使用 `EMAIL_ENABLED=true` 显式启用；`SMTP_SSL` 和
  `SMTP_STARTTLS` 不能同时开启；
- 仅开放 80/443，限制 SSH，启用系统防火墙；
- 服务器磁盘和异机备份加密；
- 容器使用非 root 用户并设置资源限制；
- 迁移在 API/worker 切换前单独执行；
- 日志不得记录稿件正文、Session、API Key 或邮件凭据；
- 定期验证备份可以恢复，而不只是检查备份任务成功。

首次上线前还必须安装 `deploy/systemd/` 中的备份和健康检查定时器，并按
`docs/deployment/backup-and-recovery-runbook.md` 完成一次临时数据库恢复演练。

## 健康、进度与邮件验证

```bash
# 进程存活
curl -fsS https://review.example.com/api/health/live

# 数据库、Redis 与上传目录就绪；该端点不向公网暴露
docker compose --env-file .env.production -f docker-compose.prod.yml \
  exec -T api python -c \
  "import os,urllib.request; h=os.environ['ALLOWED_HOSTS'].split(',')[0]; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/health/ready',headers={'Host':h}))"

# 管理员运行状态；请用正式 API Key 注入，不要写入脚本或历史记录
curl -fsS -H "X-API-Key: ${SOCIALEVAL_ADMIN_API_KEY}" \
  https://review.example.com/api/health/operations
```

管理员运行状态返回处理单元计数、停滞任务数、邮件投递计数和队列深度。API 容器
使用就绪检查，Worker 容器使用 Celery 节点响应检查。

开发环境可启动本地邮件沙箱：

```bash
docker compose --profile mail up -d mailpit
```

将开发环境 SMTP 指向 `localhost:1025`，并关闭加密；浏览器访问 `localhost:8025`
检查邮件。正式环境不得使用该服务。

## 正式启用门禁

编辑单元首次只能进入试运行。正式启用前，管理员须在后台登记验证类型、框架版本、
模型集合版本、样本清单 SHA-256、样本数和指标，完成签字后再绑定验证记录。生产
模式不接受只填样本数的自由文本替代验证记录。
