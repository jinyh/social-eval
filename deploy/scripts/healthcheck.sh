#!/usr/bin/env bash
set -euo pipefail

public_base_url="${PUBLIC_BASE_URL:?set PUBLIC_BASE_URL}"
data_root="${SOCIALEVAL_DATA_ROOT:-/srv/socialeval}"
deploy_dir="${SOCIALEVAL_DEPLOY_DIR:-/opt/socialeval}"
env_file="${SOCIALEVAL_ENV_FILE:-${deploy_dir}/.env.production}"

curl --fail --silent --show-error --max-time 15 \
  "${public_base_url%/}/api/health/live" >/dev/null

cd "${deploy_dir}"
docker compose --env-file "${env_file}" -f docker-compose.prod.yml exec -T api \
  python -c "import os, urllib.request; host=next((x.strip() for x in os.environ['ALLOWED_HOSTS'].split(',') if x.strip()), '127.0.0.1'); urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/health/ready', headers={'Host': host}), timeout=10)"

disk_percent="$(df -P "${data_root}" | awk 'NR==2 {gsub("%", "", $5); print $5}')"
if [ "${disk_percent}" -ge 85 ]; then
  echo "数据盘使用率达到 ${disk_percent}%" >&2
  exit 1
fi

backup_stamp="${data_root}/last-successful-backup"
if [ ! -f "${backup_stamp}" ]; then
  echo "尚无成功备份记录" >&2
  exit 1
fi
now="$(date +%s)"
modified="$(stat -c %Y "${backup_stamp}")"
if [ $((now - modified)) -gt 93600 ]; then
  echo "最近成功备份已经超过 26 小时" >&2
  exit 1
fi
