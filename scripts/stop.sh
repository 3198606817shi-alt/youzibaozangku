#!/bin/zsh
set -euo pipefail

APP_ROOT="${HOME}/Library/Application Support/笔记视频提取器"
APP_CODE_DIR="${APP_ROOT}/app"
APP_LOCK_DIR="${APP_ROOT}/service.lock"
APP_PID_FILE="${APP_LOCK_DIR}/pid"
APP_URL="http://127.0.0.1:8766"
APP_ENTRY="${APP_CODE_DIR}/web_app.py"

if [[ ! -f "${APP_PID_FILE}" ]]; then
  /bin/rmdir "${APP_LOCK_DIR}" 2>/dev/null || true
  exit 0
fi

SERVER_PID="$(/bin/cat "${APP_PID_FILE}" 2>/dev/null || true)"
if [[ ! "${SERVER_PID}" =~ '^[0-9]+$' ]]; then
  /bin/rm -f "${APP_PID_FILE}"
  /bin/rmdir "${APP_LOCK_DIR}" 2>/dev/null || true
  exit 0
fi

COMMAND="$(/bin/ps -p "${SERVER_PID}" -o command= 2>/dev/null || true)"
if [[ "${COMMAND}" != *"${APP_ENTRY}"* ]]; then
  /bin/rm -f "${APP_PID_FILE}"
  /bin/rmdir "${APP_LOCK_DIR}" 2>/dev/null || true
  exit 0
fi

/usr/bin/curl --silent --max-time 1 -X POST \
  -H 'Origin: http://127.0.0.1:8766' \
  -H 'Content-Type: application/json' \
  -d '{}' "${APP_URL}/api/stop" >/dev/null 2>&1 || true

# 最多等待30秒，让当前笔记在安全处理点结束；没有任务时会立即继续。
for _ in {1..60}; do
  if ! /bin/kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
  STATUS="$(/usr/bin/curl --silent --max-time 1 "${APP_URL}/api/status" 2>/dev/null || true)"
  if [[ -z "${STATUS}" || "${STATUS}" == *'"current":null'* || "${STATUS}" == *'"current": null'* ]]; then
    break
  fi
  /bin/sleep 0.5
done

/bin/kill -TERM "${SERVER_PID}" 2>/dev/null || true

for _ in {1..50}; do
  if ! /bin/kill -0 "${SERVER_PID}" 2>/dev/null; then
    break
  fi
  /bin/sleep 0.1
done

if /bin/kill -0 "${SERVER_PID}" 2>/dev/null; then
  /bin/echo "服务未能正常退出，已保留锁文件。" >&2
  exit 1
fi

/bin/rm -f "${APP_PID_FILE}"
/bin/rmdir "${APP_LOCK_DIR}" 2>/dev/null || true
