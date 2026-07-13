"""고구마런 챌린지(원형석 대결) 자동 완주 테스트.

검증된 시나리오(plusrun_challenge_원형석대결원형석gpx.py)를 pytest로 이관:
  챌린지 → 도전하기 → 가이드 → 원형석 선택 → 시작하기
  → 원형석 GPX 실시간 재생(거리 누적 + puck 이동, 페이스 현실적)
  → FINISH 자동 완주 → 결과 화면 도달을 assert.

실행: (Appium 서버 기동 후)  pytest tests/test_challenge_run.py -v -s
      배속: PLUSRUN_SPEED=6 pytest ...   (단 페이스 빨라져 기록 삭제 위험)
"""
import os
import time

import pytest

from conftest import adb, shot
from lib.gps_feeder import GpsFeeder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_W, REF_H = 1080, 2400
CTA_ENTER = (534, 1662)   # 홈 카드 'N명 도전중' 진입
CTA_BOTTOM = (534, 2172)  # 하단 주버튼(도전하기/다음/확인/선택/시작하기)
DLG_DISMISS = (346, 1350)


def _tap(driver, x_ref, y_ref):
    s = driver.get_window_size()
    driver.tap([(int(s["width"] * x_ref / REF_W), int(s["height"] * y_ref / REF_H))])


def _src(driver):
    try:
        return driver.page_source
    except Exception:
        return ""


def _click_text(driver, text):
    from appium.webdriver.common.appiumby import AppiumBy
    try:
        els = driver.find_elements(AppiumBy.ANDROID_UIAUTOMATOR,
                                   f'new UiSelector().textContains("{text}")')
        if els:
            els[0].click()
            return True
    except Exception:
        pass
    return False


def _handle_popup(driver, s):
    if "다시 보지 않기" in s or "워치 앱을 설치" in s:
        if not _click_text(driver, "다시 보지 않기"):
            _tap(driver, *DLG_DISMISS)
        time.sleep(1.2)
        return True
    if "배터리" in s and "확인" in s:
        _click_text(driver, "허용")
        time.sleep(1.0)
        if not _click_text(driver, "확인"):
            _tap(driver, *CTA_BOTTOM)
        time.sleep(1.0)
        return True
    return False


def _navigate_to_run(driver, feeder, max_steps=45):
    for _ in range(max_steps):
        s = _src(driver)
        if _handle_popup(driver, s):
            continue
        if "준비되셨다면" in s or "시작하기" in s or "코스 출발점" in s:
            feeder.set_start()          # 출발점 지오펜스 진입
            time.sleep(2)
            _tap(driver, *CTA_BOTTOM)   # 시작하기
            time.sleep(2)
            _handle_popup(driver, _src(driver))
            return True
        if "대결 상대" in s:
            _tap(driver, *CTA_BOTTOM)   # 원형석 기본 선택 → 선택
        elif "Challenge Guide" in s or "러닝 방향" in s or "FINISH" in s:
            _tap(driver, *CTA_BOTTOM)   # 가이드 다음/확인
        elif "도전하기" in s:
            _tap(driver, *CTA_BOTTOM)
        elif "도전중" in s:
            _tap(driver, *CTA_ENTER)
        time.sleep(1.6)
    return False


@pytest.mark.challenge
def test_challenge_run_complete(driver, config, artifacts_dir):
    device = config["device"]
    adb(device, "shell", "dumpsys", "deviceidle", "whitelist", "+" + config["app_package"])

    feeder = GpsFeeder(device, os.path.join(ROOT, config["gpx_file"]), speed=config["speed"])
    feeder.set_start()
    time.sleep(1)

    # 홈 로딩 대기 후 러닝 시작까지 네비게이션
    time.sleep(6)
    for _ in range(4):
        if not _handle_popup(driver, _src(driver)):
            break
        time.sleep(1)

    started = _navigate_to_run(driver, feeder)
    shot(driver, artifacts_dir, "run_start.png")
    assert started, "러닝 시작 화면까지 네비게이션 실패"

    feeder.start()
    try:
        budget = feeder.total_seconds / config["speed"] + 180
        t0 = time.time()
        finished = False
        run_seen = False
        last_shot = 0
        while time.time() - t0 < budget:
            s = _src(driver)
            _handle_popup(driver, s)
            running = "중단하기" in s
            run_seen = run_seen or running
            done = any(k in s for k in ("완주", "결과", "축하", "WIN", "LOSE",
                                        "승리", "패배", "무승부", "다시 도전", "홈으로", "WINNER"))
            el = int(time.time() - t0)
            if el - last_shot >= 60:
                shot(driver, artifacts_dir, f"run_{el:04d}s.png")
                last_shot = el
            if done or (run_seen and not running):
                finished = True
                break
            time.sleep(10)
    finally:
        feeder.stop()

    shot(driver, artifacts_dir, "result.png")
    assert finished, "완주/결과 화면에 도달하지 못함"
