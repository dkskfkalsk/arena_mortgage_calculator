#!/bin/bash
set -e
pip install -r requirements.txt
# 프로젝트 내 browsers 폴더에 Chromium 설치 (배포에 포함됨)
export PLAYWRIGHT_BROWSERS_PATH="$PWD/browsers"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
playwright install chromium
