#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="${HOME}/Library/Application Support/笔记视频提取器"
APP_CODE_DIR="${APP_ROOT}/app"
APP_VENV_DIR="${APP_ROOT}/venv"
DESKTOP_APP="${HOME}/Desktop/笔记视频提取器.app"
REQUIRED_SCOPES="base:app:read base:table:read base:field:read base:record:create base:record:read base:record:update drive:file:upload docs:document.media:upload"

pause_install() {
  /bin/echo
  /bin/echo "按回车键关闭……"
  read -r
}
trap 'CODE=$?; if [[ ${CODE} -ne 0 ]]; then /bin/echo "\n安装未完成，请按上方提示处理后重试。"; pause_install; fi' EXIT

/bin/echo "笔记视频提取器 v1.0.1 安装向导"
/bin/echo "程序页面保持原版；每位使用者必须使用自己的飞书表格、Cookie和转写密钥。"
/bin/echo

if [[ "$(/usr/bin/uname -s)" != "Darwin" ]]; then
  /bin/echo "此安装包仅支持Mac。"
  exit 1
fi

PYTHON_BIN=""
for CANDIDATE in \
  "$(command -v python3 2>/dev/null || true)" \
  "/opt/homebrew/bin/python3" \
  "/usr/local/bin/python3" \
  "${HOME}/.local/bin/python3"; do
  if [[ -x "${CANDIDATE}" ]] && "${CANDIDATE}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PYTHON_BIN="${CANDIDATE}"
    break
  fi
done
if [[ -z "${PYTHON_BIN}" ]]; then
  /bin/echo "需要Python 3.10或更高版本：https://www.python.org/downloads/macos/"
  exit 1
fi

/bin/mkdir -p "${APP_CODE_DIR}/templates" "${APP_CODE_DIR}/scripts" "${APP_ROOT}/downloads" "${APP_ROOT}/logs"
for FILE in runtime_config.py configure_app.py feishu_check.py log_safety.py web_app.py pipeline.py fetch_note.py fetch_profile.py transcribe.py requirements.txt; do
  /bin/cp "${PROJECT_DIR}/${FILE}" "${APP_CODE_DIR}/${FILE}"
done
/bin/cp "${PROJECT_DIR}/templates/index.html" "${APP_CODE_DIR}/templates/index.html"
for FILE in launch.sh stop.sh sensitive_scan.py; do
  /bin/cp "${PROJECT_DIR}/scripts/${FILE}" "${APP_CODE_DIR}/scripts/${FILE}"
done
/bin/chmod 755 "${APP_CODE_DIR}/scripts/launch.sh" "${APP_CODE_DIR}/scripts/stop.sh"

if [[ ! -x "${APP_VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${APP_VENV_DIR}"
fi
"${APP_VENV_DIR}/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"${APP_VENV_DIR}/bin/python" -m pip install --disable-pip-version-check -r "${APP_CODE_DIR}/requirements.txt"

if ! command -v node >/dev/null 2>&1 || ! command -v npx >/dev/null 2>&1; then
  /bin/echo "需要Node.js才能安装飞书官方工具：https://nodejs.org/zh-cn/download"
  exit 1
fi
if ! command -v lark-cli >/dev/null 2>&1; then
  read "REPLY?需要下载飞书官方CLI。是否继续？输入 y 继续："
  if [[ "${REPLY:-}" != "y" && "${REPLY:-}" != "Y" ]]; then
    /bin/echo "已停止安装飞书工具。"
    exit 1
  fi
  npx @larksuite/cli@latest install
  hash -r
  if ! command -v lark-cli >/dev/null 2>&1; then
    /bin/echo "飞书CLI已下载，但当前终端还找不到它。请重新打开终端后再次运行安装程序。"
    exit 1
  fi
fi

if ! lark-cli config show >/dev/null 2>&1; then
  /bin/echo "飞书将创建并配置你自己的应用，不会使用仓库所有者的账号。"
  read "REPLY?是否继续创建自己的飞书应用？输入 y 继续："
  if [[ "${REPLY:-}" != "y" && "${REPLY:-}" != "Y" ]]; then
    /bin/echo "已停止飞书应用配置。"
    exit 1
  fi
  lark-cli config init --new --lang zh_cn
fi
if ! lark-cli auth check --scope "${REQUIRED_SCOPES}" --json >/dev/null 2>&1; then
  /bin/echo "飞书将申请读取表结构、写入记录和上传封面所需的最小权限。"
  read "REPLY?是否继续飞书授权？输入 y 继续："
  if [[ "${REPLY:-}" != "y" && "${REPLY:-}" != "Y" ]]; then
    /bin/echo "已停止飞书授权。"
    exit 1
  fi
  lark-cli auth login --scope "${REQUIRED_SCOPES}"
fi

LEGACY_ARGS=()
if [[ -f "${PROJECT_DIR}/../xhs-tool/config.json" ]]; then
  LEGACY_ARGS=(--legacy-dir "${PROJECT_DIR}/../xhs-tool")
fi
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${APP_CODE_DIR}" \
  "${APP_VENV_DIR}/bin/python" "${APP_CODE_DIR}/configure_app.py" "${LEGACY_ARGS[@]}"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${APP_CODE_DIR}" \
  "${APP_VENV_DIR}/bin/python" "${APP_CODE_DIR}/configure_app.py" --check

if [[ -e "${DESKTOP_APP}" ]]; then
  /bin/echo "桌面已存在同名应用。替换应用不会删除配置和下载数据。"
  read "REPLY?是否替换？输入 y 继续："
  if [[ "${REPLY:-}" == "y" || "${REPLY:-}" == "Y" ]]; then
    /bin/rm -rf "${DESKTOP_APP}"
    /usr/bin/ditto "${PROJECT_DIR}/dist/笔记视频提取器.app" "${DESKTOP_APP}"
  fi
else
  /usr/bin/ditto "${PROJECT_DIR}/dist/笔记视频提取器.app" "${DESKTOP_APP}"
fi

/bin/echo
/bin/echo "安装完成。双击桌面的“笔记视频提取器”即可打开原版页面。"
/bin/echo "退出时请在Dock中右键应用图标并选择“退出”。"
pause_install
