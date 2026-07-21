"""엑셀 케이스의 action 키워드를 Appium 동작으로 실행하는 러너.

Compose 앱 특성상 element.click() 이 네비게이션을 안 먹는 경우가 있어,
tap_text 는 요소를 찾은 뒤 그 중심 좌표를 실제 탭(Maestro 방식)한다.
"""
import os
import time
import subprocess

from appium.webdriver.common.appiumby import AppiumBy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_W, REF_H = 1080, 2400
CTA_ENTER = (534, 1662)    # 홈 카드 'N명 도전중' 진입 좌표
CTA_BOTTOM = (534, 2172)   # 하단 주버튼 좌표(1080x2400 기준)
DLG_DISMISS = (346, 1350)

# 액션 레지스트리 — 대시보드/러너/문서가 공유하는 단일 소스.
# 신규 action 추가 시: (1) KeywordRunner 에 메서드 추가 (2) 여기에 한 줄 등록.
ACTIONS = {
    "launch":            {"desc": "앱 새로 실행(로그인 우회)+홈 대기", "needs_target": False},
    "tap_text":          {"desc": "target 텍스트 요소를 찾아 탭",       "needs_target": True,  "target_hint": "화면 텍스트"},
    "tap_bottom":        {"desc": "하단 주버튼 탭",                      "needs_target": False},
    "back":              {"desc": "안드로이드 뒤로가기",                 "needs_target": False},
    "wait":              {"desc": "target(초)만큼 대기",                "needs_target": True,  "target_hint": "초"},
    "assert_visible":    {"desc": "target 텍스트가 보이면 통과",         "needs_target": True,  "target_hint": "기대 텍스트"},
    "assert_not_visible":{"desc": "target 텍스트가 없으면 통과",         "needs_target": True,  "target_hint": "사라질 텍스트"},
    "start_challenge":   {"desc": "챌린지 진입~시작하기 자동",            "needs_target": False},
    "play_gpx":          {"desc": "GPX 배속 재생→완주/결과 대기",         "needs_target": True,  "target_hint": "배속(예:1.15)"},
}


class KeywordRunner:
    def __init__(self, driver, config, adb_path):
        self.d = driver
        self.cfg = config
        self.adb = adb_path

    # ---- 저수준 ----
    def _src(self):
        try:
            return self.d.page_source
        except Exception:
            return ""

    def _tap_xy(self, x, y):
        self.d.tap([(int(x), int(y))])

    def _tap_frac(self, xr, yr):
        s = self.d.get_window_size()
        self._tap_xy(s["width"] * xr / REF_W, s["height"] * yr / REF_H)

    def _adb(self, *args):
        subprocess.run([self.adb, "-s", self.cfg["device"], *args],
                       check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---- 키워드 ----
    def launch(self, _target):
        pkg = self.cfg["app_package"]
        self._adb("shell", "dumpsys", "deviceidle", "whitelist", "+" + pkg)
        self._adb("shell", "am", "force-stop", pkg)
        self._adb("shell", "am", "start", "-n", f"{pkg}/{self.cfg['app_activity']}",
                  "--es", "e2e_login_email", self.cfg["login_email"])
        # 홈 로딩 대기(최대 40s): '도전중' 이 보이면 완료
        for _ in range(40):
            if "도전중" in self._src():
                break
            time.sleep(1)
        time.sleep(1)

    def tap_text(self, target):
        # 요소 찾아 중심 좌표 탭(없으면 실패)
        els = self.d.find_elements(
            AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{target}")')
        if not els:
            raise AssertionError(f"tap_text: '{target}' 요소를 찾지 못함")
        r = els[0].rect
        self._tap_xy(r["x"] + r["width"] / 2, r["y"] + r["height"] / 2)
        time.sleep(2.5)

    def tap_bottom(self, _target):
        self._tap_frac(*CTA_BOTTOM)
        time.sleep(2.5)

    def back(self, _target):
        self._adb("shell", "input", "keyevent", "4")
        time.sleep(1.5)

    def wait(self, target):
        time.sleep(float(target or 1))

    def assert_visible(self, target):
        assert target in self._src(), f"assert_visible 실패: '{target}' 이(가) 화면에 없음"

    def assert_not_visible(self, target):
        assert target not in self._src(), f"assert_not_visible 실패: '{target}' 이(가) 화면에 여전히 보임"

    # ---- 팝업 자동 처리(챌린지 진입 중 끼어드는 다이얼로그) ----
    def _click_text(self, text):
        try:
            els = self.d.find_elements(
                AppiumBy.ANDROID_UIAUTOMATOR, f'new UiSelector().textContains("{text}")')
            if els:
                els[0].click()
                return True
        except Exception:
            pass
        return False

    def _handle_popup(self, s):
        if "다시 보지 않기" in s or "워치 앱을 설치" in s:
            if not self._click_text("다시 보지 않기"):
                self._tap_frac(*DLG_DISMISS)
            time.sleep(1.2)
            return True
        if "배터리" in s and "확인" in s:
            self._click_text("허용")
            time.sleep(1.0)
            if not self._click_text("확인"):
                self._tap_frac(*CTA_BOTTOM)
            time.sleep(1.0)
            return True
        return False

    def _course_start(self):
        """GPX 첫 지점(lon, lat) — 출발 지오펜스 진입용."""
        from lib.gps_feeder import load_gpx
        pts = load_gpx(os.path.join(ROOT, self.cfg["gpx_file"]))
        return (pts[0][0], pts[0][1]) if pts else None

    def _geo_fix(self, lon, lat):
        self._adb("emu", "geo", "fix", lon, lat, "8")

    # ---- 챌린지 진입: 카드→도전하기→가이드→원형석 선택→시작하기 ----
    def start_challenge(self, _target):
        start = self._course_start()
        for _ in range(45):
            s = self._src()
            if self._handle_popup(s):
                continue
            if "준비되셨다면" in s or "시작하기" in s or "코스 출발점" in s:
                if start:                            # 출발점(초록 원) 진입
                    self._geo_fix(*start); time.sleep(2)
                self._tap_frac(*CTA_BOTTOM)          # 시작하기
                time.sleep(2)
                self._handle_popup(self._src())
                return
            if "대결 상대" in s:
                self._tap_frac(*CTA_BOTTOM)          # 원형석 기본 선택 → 선택
            elif "Challenge Guide" in s or "러닝 방향" in s or "FINISH" in s:
                self._tap_frac(*CTA_BOTTOM)          # 가이드 다음/확인
            elif "도전하기" in s:
                self._tap_frac(*CTA_BOTTOM)
            elif "도전중" in s:
                self._tap_frac(*CTA_ENTER)           # 홈 카드 진입
            time.sleep(1.6)
        raise AssertionError("start_challenge: 러닝 시작 화면까지 도달 실패")

    # ---- GPX 실시간 재생(거리 누적) 후 완주/결과까지 대기 ----
    def play_gpx(self, target):
        # target = 재생 배속(비우면 1.0). 배속↑ → 페이스 빨라짐(승리), ↓ → 느려짐(패배)
        from lib.gps_feeder import GpsFeeder
        speed = float(target) if target else 1.0
        gpx = os.path.join(ROOT, self.cfg["gpx_file"])
        feeder = GpsFeeder(self.cfg["device"], gpx, speed=speed)
        feeder.start()
        try:
            budget = feeder.total_seconds / speed + 180
            t0 = time.time()
            while time.time() - t0 < budget:
                s = self._src()
                self._handle_popup(s)
                if any(k in s for k in ("WINNER","WIN","LOSE","결과","완주","축하",
                                        "승리","패배","무승부","다시 도전","홈으로")):
                    return
                time.sleep(8)
        finally:
            feeder.stop()
        raise AssertionError("play_gpx: 완주/결과 화면에 도달하지 못함")

    def run_step(self, action, target):
        # 내장 액션(레지스트리에 등록된 것)만 메서드로 디스패치
        if action in ACTIONS:
            getattr(self, action)(target)
            return
        # 사용자 정의 액션(custom_actions.py) 디스패치
        try:
            from lib.actionstore import load_custom_funcs
            funcs = load_custom_funcs()
        except Exception:
            funcs = {}
        if action in funcs:
            funcs[action](self, target)
            return
        raise AssertionError(f"알 수 없는 action: {action}")
