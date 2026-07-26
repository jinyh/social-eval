#!/usr/bin/env bash
set -euo pipefail
umask 077

deploy_dir="${SOCIALEVAL_DEPLOY_DIR:-/opt/socialeval}"
env_file="${SOCIALEVAL_ENV_FILE:-${deploy_dir}/.env.production}"
data_root="${SOCIALEVAL_DATA_ROOT:-/srv/socialeval}"
stage_dir="${data_root}/backup-stage"
backup_id="$(date -u +%Y%m%dT%H%M%SZ)"
dump_path="${stage_dir}/postgres-${backup_id}.dump"

mkdir -p "${stage_dir}"
cd "${deploy_dir}"

docker compose --env-file "${env_file}" -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-socialeval}" -d "${POSTGRES_DB:-socialeval}" -Fc \
  > "${dump_path}"
docker compose --env-file "${env_file}" -f docker-compose.prod.yml exec -T postgres \
  pg_restore --list < "${dump_path}" >/dev/null

restic backup "${dump_path}" "${data_root}/app" \
  --tag socialeval-production
restic forget --prune --keep-daily 7 --keep-weekly 8 --keep-monthly 6 \
  --tag socialeval-production

touch "${data_root}/last-successful-backup"
find "${stage_dir}" -type f -name 'postgres-*.dump' -mtime +2 -delete
