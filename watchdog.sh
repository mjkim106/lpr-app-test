#!/bin/bash
# 대시보드 서버 워치독: 30초마다 살아있는지 검사하고 죽었으면 자동 재시작.
# 사용:  nohup ./watchdog.sh >/dev/null 2>&1 &   (또는 백그라운드 실행)
# 중지:  pkill -f watchdog.sh   (그리고 pkill -f dashboard/app.py)
cd "$(dirname "$0")"
PORT="${PLUSRUN_PORT:-5050}"
LOG="artifacts/dashboard.log"
mkdir -p artifacts
export PLUSRUN_HOST=0.0.0.0 PLUSRUN_PORT="$PORT"
while true; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 4 "http://127.0.0.1:$PORT/" 2>/dev/null)
  if [ "$code" != "200" ]; then
    echo "[$(date '+%F %T')] 서버 응답없음(code=$code) → 재시작" >> "$LOG"
    pkill -f "dashboard/app.py" 2>/dev/null
    sleep 1
    nohup /usr/bin/python3 dashboard/app.py >> "$LOG" 2>&1 &
    sleep 4
  fi
  sleep 30
done
