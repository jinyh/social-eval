# SocialEval 备份与恢复运行手册

## 目标与范围

- 恢复点目标：不超过 24 小时。
- 恢复时间目标：不超过 4 小时。
- 范围：PostgreSQL、`/srv/socialeval/app`、发布版本和必要配置。
- Redis 不是权威数据源，不代替 PostgreSQL 与文件备份。

## 首次配置

1. 在交大云创建私有 S3 存储空间。
2. 安装 Restic，将 `deploy/backup.env.example` 复制到
   `/etc/socialeval/backup.env`，权限设为 `0600`。
3. 将 Restic 仓库密码单独写入 `/etc/socialeval/restic-password`，权限设为
   `0600`；该密码必须由另一名责任人离线保管副本。
4. 执行 `restic init`，再手工运行一次 `deploy/scripts/backup.sh`。
5. 安装并启用 `socialeval-backup.timer`。
6. 在交大云控制台为独立数据盘设置每日自动快照，并建立位于不同存储池的云硬盘备份。

备份脚本先生成 PostgreSQL 自定义格式逻辑备份并用 `pg_restore --list`
检查，再由 Restic 客户端加密数据库备份和应用文件后上传。保留 7 个每日、
8 个每周和 6 个每月备份。

## 日常检查

```bash
systemctl status socialeval-backup.timer
journalctl -u socialeval-backup.service --since today
restic snapshots --tag socialeval-production
restic check
```

每周运行 `restic check`。备份超过 26 小时未成功时，健康检查必须告警。

## 恢复演练

1. 记录目标快照、Restic 快照和应用 Git commit。
2. 在临时目录执行 `restic restore`，不得直接覆盖生产数据。
3. 用恢复出的 dump 创建临时 PostgreSQL：

```bash
createdb socialeval_restore_test
pg_restore --exit-on-error --no-owner \
  --dbname socialeval_restore_test postgres-<backup-id>.dump
```

4. 校验 Alembic 版本、用户数、投稿数、审计数及抽样文件 SHA-256。
5. 用临时应用实例验证登录、稿件读取和报告读取。
6. 记录总耗时；超过 4 小时即视为恢复目标未通过。

## 生产恢复

生产恢复必须在维护窗口执行，并由两人核对目标：

1. 停止 `api`、`worker`，保留 PostgreSQL 运行。
2. 为当前数据盘和数据库再做一次保护性快照。
3. 将 Restic 内容恢复到临时路径并验证。
4. 恢复 PostgreSQL 和 `/srv/socialeval/app`。
5. 运行迁移检查、生产配置自检和完整冒烟。
6. 确认无误后恢复入口；原故障数据保留到事件复盘完成。

不得使用 `alembic downgrade` 代替数据恢复。
