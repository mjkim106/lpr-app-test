# PLUS RUN — Appium E2E 테스트

Android 앱(PLUS RUN, stg 디버그 빌드)을 Appium으로 자동 테스트한다.
현재 검증된 시나리오: **고구마런 챌린지 원형석 대결 완주**(실시간 GPX 재생으로 거리 누적·완주·기록).

## 구조
```
conftest.py                # Appium 드라이버 fixture, 설정 로딩, 스크린샷 헬퍼
config.yaml                # device/app/login/gpx/speed (환경변수로 override)
lib/gps_feeder.py          # GPX 실시간 GPS 피더(속도 포함 geo fix)
data/goguma_course.gpx     # 원형석 코스 GPX
tests/test_challenge_run.py# 챌린지 완주 테스트
run.sh                     # Appium 확인 후 pytest 실행
기타/                       # 정리 전 옛 파일들(git 추적 제외)
```

## 사전 준비
1. Android 에뮬레이터/기기에 **디버그 빌드** 설치 (`com.hanwha.plus.pr.stg`, DEBUGGABLE)
   - 릴리스 빌드는 `e2e_login_email` 등 디버그 훅이 동작하지 않음
   - 빌드: `MAPBOX_ACCESS_TOKEN=<pk...> ./gradlew :app:assembleStgDebug` (lpr-android)
2. Appium 서버 기동: 새 터미널에서 `cd ~ && appium`
3. 의존성: `pip install -r requirements.txt`

## 실행
```bash
./run.sh                          # 전체
./run.sh tests/test_challenge_run.py -s
PLUSRUN_SPEED=6 ./run.sh          # 배속(단 페이스 빨라져 기록 삭제 위험 → 검증은 SPEED=1 권장)
PLUSRUN_DEVICE=emulator-5554 PLUSRUN_EMAIL=someone@naver.com ./run.sh
```
스크린샷은 `artifacts/<타임스탬프>/` 에 저장된다.

## 참고
- 실시간(SPEED=1) 실행은 약 26.5분(코스 7.97km / 3'20"/km) 소요.
- `geo fix` 5번째 인자(knots 속도)가 핵심 — 없으면 앱 정지필터에 걸려 거리가 0으로 남음.
