#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
RELEASE_NAME="笔记视频提取器-v1.0.1-mac"
RELEASE_ZIP="${DIST_DIR}/${RELEASE_NAME}.zip"
CHECKSUM_FILE="${DIST_DIR}/${RELEASE_NAME}.sha256"
STAGING_ROOT="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/note-extractor-release.XXXXXX")"
STAGING_DIR="${STAGING_ROOT}/${RELEASE_NAME}"

cleanup() {
  /bin/rm -rf "${STAGING_ROOT}"
}
trap cleanup EXIT INT TERM

"${PROJECT_DIR}/scripts/build_macos_app.sh" >/dev/null
/bin/mkdir -p "${STAGING_DIR}/templates" "${STAGING_DIR}/scripts" "${STAGING_DIR}/dist"

for FILE in \
  README.md USE_POLICY.md SECURITY.md LICENSE THIRD_PARTY_NOTICES.md CHANGELOG.md \
  requirements.txt config.example.json "安装.command" \
  runtime_config.py configure_app.py feishu_check.py log_safety.py web_app.py pipeline.py \
  fetch_note.py fetch_profile.py transcribe.py; do
  /bin/cp "${PROJECT_DIR}/${FILE}" "${STAGING_DIR}/${FILE}"
done

/bin/cp "${PROJECT_DIR}/templates/index.html" "${STAGING_DIR}/templates/index.html"
for FILE in launch.sh stop.sh sensitive_scan.py; do
  /bin/cp "${PROJECT_DIR}/scripts/${FILE}" "${STAGING_DIR}/scripts/${FILE}"
done
/usr/bin/ditto "${PROJECT_DIR}/dist/笔记视频提取器.app" "${STAGING_DIR}/dist/笔记视频提取器.app"

/usr/bin/find "${STAGING_DIR}" -type d -name '__pycache__' -prune -exec /bin/rm -rf {} +
/usr/bin/find "${STAGING_DIR}" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 "${PROJECT_DIR}/scripts/sensitive_scan.py" "${STAGING_DIR}"
/bin/rm -f "${RELEASE_ZIP}" "${CHECKSUM_FILE}"
/usr/bin/python3 "${PROJECT_DIR}/scripts/make_zip.py" "${STAGING_DIR}" "${RELEASE_ZIP}"
cd "${DIST_DIR}"
/usr/bin/shasum -a 256 "${RELEASE_NAME}.zip" > "${RELEASE_NAME}.sha256"
/bin/echo "${RELEASE_ZIP}"
