#!/bin/bash
# Appium 서버 기동 확인 후 pytest 실행. 사용: ./run.sh [pytest 인자]
set -e
cd "$(dirname "$0")"
if ! curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4723/status 2>/dev/null | grep -q 200; then
  echo "Appium 서버가 없습니다. 새 터미널에서 'cd ~ && appium' 로 먼저 기동하세요." >&2
  exit 1
fi
[ -d .venv ] && source .venv/bin/activate 2>/dev/null || true
pytest "$@"
