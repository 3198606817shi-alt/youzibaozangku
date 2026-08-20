#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="${PROJECT_DIR}/dist"
APP_PATH="${DIST_DIR}/笔记视频提取器.app"
SOURCE_SCRIPT="${PROJECT_DIR}/scripts/AppLauncher.applescript"
ICON_SOURCE="${DIST_DIR}/AppIcon.icns"

/bin/mkdir -p "${DIST_DIR}"
/bin/rm -rf "${APP_PATH}"
/usr/bin/osacompile -s -o "${APP_PATH}" "${SOURCE_SCRIPT}"
/bin/cp "${ICON_SOURCE}" "${APP_PATH}/Contents/Resources/AppIcon.icns"

/usr/bin/plutil -replace CFBundleName -string "笔记视频提取器" "${APP_PATH}/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleDisplayName -string "笔记视频提取器" "${APP_PATH}/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleIdentifier -string "com.youzi.note-video-extractor" "${APP_PATH}/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleShortVersionString -string "1.0.0" "${APP_PATH}/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleVersion -string "1" "${APP_PATH}/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleIconFile -string "AppIcon" "${APP_PATH}/Contents/Info.plist"
/usr/bin/plutil -remove CFBundleIconName "${APP_PATH}/Contents/Info.plist" 2>/dev/null || true
/usr/bin/codesign --force --deep --sign - "${APP_PATH}" >/dev/null
/bin/echo "${APP_PATH}"
