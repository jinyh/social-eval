# SocialEval 生产环境变量说明

生产环境清单的唯一模板是仓库根目录 `.env.production.example`。复制为
`.env.production` 后在部署主机填写，文件权限必须为 `0600`，不得提交 Git。

## 必填安全项

- `APP_ENV=production`
- `APP_DOMAIN`、`PUBLIC_BASE_URL`、`ALLOWED_HOSTS`、`ALLOWED_ORIGINS`
- `SOCIALEVAL_DATA_ROOT=/srv/socialeval`
- 独立生成的 `SECRET_KEY` 与 `FIELD_ENCRYPTION_KEY`，均至少 32 个字符
- `SESSION_HTTPS_ONLY=true`
- `SESSION_MAX_AGE_SECONDS` 不超过 43200
- `ADMIN_MFA_REQUIRED=true`
- `EMAIL_ENABLED=true` 及有效 SMTP 配置
- PostgreSQL 连接和获授权模型供应商凭据

`FIELD_ENCRYPTION_KEY` 用于 TOTP 密钥和邮件队列中的一次性令牌，不能与
`SECRET_KEY` 或备份密码复用。更换该密钥前必须制定字段重新加密方案。

## 当前存储边界

应用当前只支持本地文件接口，论文和报告位于
`${SOCIALEVAL_DATA_ROOT}/app`。交大云对象存储只作为 Restic 加密备份目标，
其凭据放在 `/etc/socialeval/backup.env`，不能填写到应用环境变量。

## 自检

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm \
  api python scripts/check_production_readiness.py
```

检查只输出缺失或不合规的变量名，不输出任何凭据值。
