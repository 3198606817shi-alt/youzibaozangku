#!/bin/zsh
set -euo pipefail

APP_ROOT="${HOME}/Library/Application Support/笔记视频提取器"
APP_CODE_DIR="${APP_ROOT}/app"
APP_VENV_DIR="${APP_ROOT}/venv"
APP_LOCK_DIR="${APP_ROOT}/service.lock"
APP_PID_FILE="${APP_LOCK_DIR}/pid"
APP_LOG_DIR="${APP_ROOT}/logs"
APP_PORT="8766"
APP_URL="http://127.0.0.1:${APP_PORT}"
APP_ENTRY="${APP_CODE_DIR}/web_app.py"

/bin/mkdir -p "${APP_LOG_DIR}"

is_our_service() {
  /usr/bin/curl --silent --fail --max-time 1 "${APP_URL}/api/health" 2>/dev/null \
    | /usr/bin/grep -q '"service"[[:space:]]*:[[:space:]]*"xhs-data-extractor"'
}

open_page() {
  if [[ "${NOTE_EXTRACTOR_NO_OPEN:-0}" != "1" ]]; then
    /usr/bin/open "${APP_URL}"
  fi
}

if is_our_service; then
  open_page
  exit 0
fi

if /usr/sbin/lsof -nP -iTCP:"${APP_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  /usr/bin/osascript -e 'display alert "端口被占用" message "8766端口正被其他程序使用，本工具没有启动。" as critical' 2>/dev/null || true
  exit 1
fi

if ! /bin/mkdir "${APP_LOCK_DIR}" 2>/dev/null; then
  if [[ -f "${APP_PID_FILE}" ]]; then
    OLD_PID="$(/bin/cat "${APP_PID_FILE}" 2>/dev/null || true)"
    if [[ "${OLD_PID}" =~ '^[0-9]+$' ]] && /bin/kill -0 "${OLD_PID}" 2>/dev/null; then
      for _ in {1..25}; do
        if is_our_service; then
          open_page
          exit 0
        fi
        /bin/sleep 0.2
      done
      exit 1
    fi
  fi
  /bin/rm -f "${APP_PID_FILE}"
  /bin/rmdir "${APP_LOCK_DIR}" 2>/dev/null || true
  /bin/mkdir "${APP_LOCK_DIR}"
fi

cleanup_lock() {
  /bin/rm -f "${APP_PID_FILE}"
  /bin/rmdir "${APP_LOCK_DIR}" 2>/dev/null || true
}
trap cleanup_lock EXIT INT TERM

if [[ ! -x "${APP_VENV_DIR}/bin/python" || ! -f "${APP_ENTRY}" ]]; then
  /usr/bin/osascript -e 'display alert "尚未完成安装" message "请先双击安装包中的“安装.command”。" as critical' 2>/dev/null || true
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${APP_CODE_DIR}" \
  "${APP_VENV_DIR}/bin/python" "${APP_ENTRY}" >>"${APP_LOG_DIR}/service.log" 2>&1 &
SERVER_PID=$!
/bin/echo "${SERVER_PID}" > "${APP_PID_FILE}"

for _ in {1..50}; do
  if is_our_service; then
    open_page
    wait "${SERVER_PID}"
    exit $?
  fi
  if ! /bin/kill -0 "${SERVER_PID}" 2>/dev/null; then
    exit 1
  fi
  /bin/sleep 0.2
done

/bin/kill -TERM "${SERVER_PID}" 2>/dev/null || true
exit 1
