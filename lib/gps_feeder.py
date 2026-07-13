"""GPX 실시간 GPS 피더.

원형석 GPX(data/goguma_course.gpx)를 타임스탬프 간격대로 재생하며,
구간 속도(knots)를 실어 `adb emu geo fix <lon> <lat> 8 12 <knots>` 로 주입한다.
velocity 인자가 location.speed 를 채워 앱의 정지필터(속도<0.8m/s)를 통과 →
거리 누적 + 내 위치 아이콘(puck) 이동 + 페이스 현실적(기록 삭제 안 됨).
"""
import os
import re
import math
import time
import threading
import subprocess
from datetime import datetime

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")


def _hav(a, b):
    R = 6371000
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _parse_t(s):
    s = s.replace("Z", "")
    fmt = "%Y-%m-%dT%H:%M:%S.%f" if "." in s else "%Y-%m-%dT%H:%M:%S"
    return datetime.strptime(s, fmt)


def load_gpx(path):
    """→ [(lon, lat, t_offset_sec, knots), ...] 구간 속도 포함."""
    txt = open(path, encoding="utf-8").read()
    pts = re.findall(r'lat="([0-9.]+)"\s+lon="([0-9.]+)"', txt)
    times = re.findall(r"<time>([^<]+)</time>", txt)
    times = times[-len(pts):]
    t0 = _parse_t(times[0])
    out, prev, prev_t = [], None, 0.0
    for (lat, lon), ts in zip(pts, times):
        toff = (_parse_t(ts) - t0).total_seconds()
        cur = (float(lat), float(lon))
        mps = _hav(prev, cur) / (toff - prev_t) if (prev and toff > prev_t) else 3.0
        mps = max(1.0, min(11.0, mps))          # 앱 게이트 [0.8,12] m/s 안으로 클램프
        out.append((lon, lat, toff, mps * 1.94384))  # m/s → knots
        prev, prev_t = cur, toff
    return out


class GpsFeeder:
    """백그라운드 스레드로 GPX 를 실시간(SPEED 배속) 재생."""

    def __init__(self, device, gpx_path, speed=1.0):
        self.device = device
        self.points = load_gpx(gpx_path)
        self.speed = speed
        self._stop = threading.Event()
        self._thread = None
        self.idx = 0

    @property
    def total_seconds(self):
        return self.points[-1][2] if self.points else 0

    def _geofix(self, lon, lat, knots=None):
        cmd = [ADB, "-s", self.device, "emu", "geo", "fix", lon, lat, "8"]
        if knots is not None:
            cmd += ["12", f"{knots:.2f}"]
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def set_start(self):
        """출발점(초록 원) 진입용 — 러닝 시작 전 위치 고정."""
        if self.points:
            self._geofix(self.points[0][0], self.points[0][1])

    def _run(self):
        t_start = time.monotonic()
        for i, (lon, lat, toff, knots) in enumerate(self.points):
            if self._stop.is_set():
                break
            target = t_start + toff / self.speed
            while not self._stop.is_set():
                dt = target - time.monotonic()
                if dt <= 0:
                    break
                self._stop.wait(min(dt, 1.0))
            self._geofix(lon, lat, knots)
            self.idx = i + 1
        if self.points:
            self._geofix(self.points[-1][0], self.points[-1][1], 1.94)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
