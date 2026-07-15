# SocialEval 备份与恢复运行手册

> 当前仓库不提供自动备份脚本。生产环境应优先使用托管 PostgreSQL、Redis 与对象存储的快照/版本控制能力；以下命令仅适用于单机 Docker Compose 试点环境。

## 备份范围

- PostgreSQL：论文、评分、用户、复核与审计数据。
- `appdata`：仅在使用本地文件存储时备份。
- Redis：任务队列可重建时不作为权威数据源；确需恢复时使用平台快照。
- S3/对象存储：通过 bucket 版本控制和生命周期策略独立保护。

## 创建 PostgreSQL 逻辑备份

先停止 API、worker 等写入服务并保持 PostgreSQL 运行，然后执行：

```bash
backup_id="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "backups/${backup_id}"
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U socialeval -d socialeval -Fc \
  > "backups/${backup_id}/postgres.dump"
sha256sum "backups/${backup_id}/postgres.dump" \
  > "backups/${backup_id}/SHA256SUMS"
```

将备份复制到部署主机之外，并验证摘要：

```bash
sha256sum -c "backups/${backup_id}/SHA256SUMS"
pg_restore --list "backups/${backup_id}/postgres.dump" >/dev/null
```

## 恢复前检查

恢复是破坏性操作，必须在维护窗口内完成，并满足：

1. 业务方确认目标备份 ID 和恢复点。
2. API、worker、frontend、nginx 等入口全部停止。
3. 当前数据库另做一次快照或逻辑备份。
4. `SHA256SUMS` 与 `pg_restore --list` 校验通过。
5. PostgreSQL 用户名、数据库名和目标环境已由两人复核。

## 执行恢复

先在临时数据库演练并完成应用冒烟测试；生产恢复应由运维人员按平台流程执行。单机试点可在确认目标无误后使用：

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U socialeval -d socialeval \
  -v ON_ERROR_STOP=1 -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U socialeval -d socialeval --no-owner --exit-on-error \
  < "backups/<backup-id>/postgres.dump"
```

恢复后依次运行数据库迁移检查、API 健康检查、登录/上传/评测冒烟测试，再开放入口。对象存储与 Redis 的恢复遵循各自平台的快照流程，不与 PostgreSQL 命令混用。
