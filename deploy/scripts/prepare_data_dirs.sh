#!/usr/bin/env bash
set -euo pipefail

data_root="${SOCIALEVAL_DATA_ROOT:?set SOCIALEVAL_DATA_ROOT}"
if [[ "${data_root}" != /srv/* || "${data_root}" == "/srv" ]]; then
  echo "SOCIALEVAL_DATA_ROOT 必须是 /srv 下的专用子目录" >&2
  exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 sudo 执行，以便设置容器所需的目录所有权" >&2
  exit 1
fi

install -d -m 0750 "${data_root}"
install -d -m 0700 -o 70 -g 70 "${data_root}/postgres"
install -d -m 0750 -o 999 -g 1000 "${data_root}/redis"
install -d -m 0750 -o 10001 -g 10001 "${data_root}/app"
install -d -m 0700 "${data_root}/backup-stage"
install -d -m 0750 "${data_root}/caddy/data" "${data_root}/caddy/config"

echo "生产数据目录已创建并设置最小必要权限：${data_root}"
