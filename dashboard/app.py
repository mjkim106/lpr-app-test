"""테스트 케이스 관리 + 실행 결과 대시보드 (로컬 웹).

- 엑셀 업로드 → 테스트 자동 표시 (data/testcases.xlsx 로 저장 후 파싱)
- 테스트 목록 조회 → 클릭 시 액션 조합(스텝) 조회/수정/저장
- ▶ 실행 → pytest -k <TC> 실행(백그라운드 스레드) → 결과/날짜/소요시간을 이력에 기록
- 액션 팔레트는 lib.keywords.ACTIONS 에서 자동 생성

실행:  python3 dashboard/app.py   → http://127.0.0.1:5000
"""
import os
import sys
import json
import time
import threading
import subprocess
import datetime as dt
import xml.etree.ElementTree as ET

import re as _re
import yaml
from flask import Flask, jsonify, request, send_from_directory, abort

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import casestore              # noqa: E402
from lib import actionstore            # noqa: E402
from lib.keywords import ACTIONS       # noqa: E402

XLSX = os.path.join(ROOT, "data", "testcases.xlsx")
HISTORY = os.path.join(ROOT, "data", "run_history.json")
ARTIFACTS = os.path.join(ROOT, "artifacts")
SHOTS = os.path.join(ARTIFACTS, "shots")
FRAMES = os.path.join(ARTIFACTS, "frames")
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
MAX_FRAMES = 150          # 캡처 상한(디스크/시간 보호)
GIF_MAX = 60              # GIF 프레임 상한(초과 시 균등 샘플)
_lock = threading.Lock()


def _device():
    try:
        with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
            return os.environ.get("PLUSRUN_DEVICE", yaml.safe_load(f).get("device", "emulator-5554"))
    except Exception:
        return "emulator-5554"


def _capture(run_id):
    """실행 종료 시점의 기기 화면을 artifacts/shots/<run_id>.png 로 캡처(폴백)."""
    os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, run_id + ".png")
    try:
        with open(path, "wb") as f:
            subprocess.run([ADB, "-s", _device(), "exec-out", "screencap", "-p"],
                           stdout=f, stderr=subprocess.DEVNULL, timeout=15)
        return os.path.getsize(path) > 0
    except Exception:
        return False


def _grab_png(device):
    p = subprocess.run([ADB, "-s", device, "exec-out", "screencap", "-p"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
    return p.stdout


def _capture_frames(run_id, stop_ev):
    """실행 중 2초마다 화면을 캡처(다운스케일)해 GIF 프레임으로 저장."""
    try:
        from PIL import Image
        from io import BytesIO
    except Exception:
        return
    dev = _device()
    d = os.path.join(FRAMES, run_id)
    os.makedirs(d, exist_ok=True)
    i = 0
    while not stop_ev.is_set() and i < MAX_FRAMES:
        try:
            raw = _grab_png(dev)
            im = Image.open(BytesIO(raw)).convert("RGB")
            im.thumbnail((360, 800))
            im.save(os.path.join(d, f"{i:04d}.png"))
            i += 1
        except Exception:
            pass
        stop_ev.wait(2)


def _make_gif(run_id):
    """캡처한 프레임들을 artifacts/shots/<run_id>.gif 로 합성."""
    try:
        from PIL import Image
        import glob as _glob
        import shutil as _shutil
    except Exception:
        return False
    d = os.path.join(FRAMES, run_id)
    files = sorted(_glob.glob(os.path.join(d, "*.png")))
    if len(files) < 2:
        return False
    if len(files) > GIF_MAX:  # 균등 샘플
        idx = sorted({round(k * (len(files) - 1) / (GIF_MAX - 1)) for k in range(GIF_MAX)})
        files = [files[j] for j in idx]
    try:
        frames = [Image.open(f).convert("P", palette=Image.ADAPTIVE) for f in files]
        os.makedirs(SHOTS, exist_ok=True)
        gif = os.path.join(SHOTS, run_id + ".gif")
        # loop 미지정 → 1회만 재생하고 멈춤(재생 반복은 프론트 '재실행' 버튼으로)
        frames[0].save(gif, save_all=True, append_images=frames[1:],
                       duration=450, optimize=True, disposal=2)
        _shutil.rmtree(d, ignore_errors=True)  # 프레임 정리
        return True
    except Exception:
        return False

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))


# ---------- 이력 저장/로드 ----------
def _load_history():
    if not os.path.exists(HISTORY):
        return []
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(items):
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _update_run(run_id, **fields):
    with _lock:
        items = _load_history()
        for it in items:
            if it["id"] == run_id:
                it.update(fields)
                break
        _save_history(items)


# ---------- 라우트 ----------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/actions")
def api_actions():
    # 케이스 편집기용: {name: meta} (내장+사용자 통합)
    merged = {}
    for a in actionstore.list_all():
        merged[a["name"]] = {"desc": a["desc"], "needs_target": a["needs_target"],
                             "target_hint": a["target_hint"], "type": a["type"]}
    return jsonify(merged)


@app.route("/api/actions/list")
def api_actions_list():
    # 액션 관리 화면용: 배열(type 포함)
    return jsonify(actionstore.list_all())


@app.route("/api/actions/<name>/code")
def api_action_code(name):
    return jsonify(actionstore.get_code(name))


@app.route("/api/actions", methods=["POST"])
def api_action_upsert():
    d = request.get_json(force=True)
    try:
        actionstore.upsert(d["name"], d["code"], d.get("desc", ""),
                           d.get("needs_target", True), d.get("target_hint", ""))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/actions/<name>", methods=["DELETE"])
def api_action_delete(name):
    try:
        actionstore.delete(name)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/cases")
def api_cases():
    try:
        return jsonify(casestore.load())
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/cases", methods=["POST"])
def api_save_all():
    cases = request.get_json(force=True)
    casestore.save(cases)
    return jsonify({"ok": True, "count": len(cases)})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """엑셀 업로드 → data/testcases.xlsx 로 저장 → 파싱된 케이스 반환."""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "파일이 없습니다"}), 400
    os.makedirs(os.path.dirname(XLSX), exist_ok=True)
    f.save(XLSX)
    try:
        cases = casestore.load()
    except Exception as e:
        return jsonify({"error": f"엑셀 파싱 실패: {e}"}), 400
    return jsonify({"ok": True, "count": len(cases), "cases": cases})


@app.route("/api/history")
def api_history():
    items = sorted(_load_history(), key=lambda x: x.get("started", ""), reverse=True)
    return jsonify(items)


@app.route("/api/latest")
def api_latest():
    """TC별 최신 실행 결과 {tc: {status, started, ended, duration}}."""
    latest = {}
    for it in sorted(_load_history(), key=lambda x: x.get("started", "")):
        latest[it["tc"]] = {"status": it.get("status"), "started": it.get("started"),
                            "ended": it.get("ended"), "duration": it.get("duration")}
    return jsonify(latest)


def _run_worker(run_id, tc):
    junit = os.path.join(ARTIFACTS, f"junit_{run_id}.xml")
    os.makedirs(ARTIFACTS, exist_ok=True)
    t0 = time.time()
    env = {**os.environ, "PLUSRUN_RUN_ID": run_id}  # 테스트가 이 id로 스크린샷 저장
    # 실행 중 프레임 캡처(GIF용) 시작
    stop_ev = threading.Event()
    cap = threading.Thread(target=_capture_frames, args=(run_id, stop_ev), daemon=True)
    cap.start()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_from_excel.py",
         "-k", tc, f"--junitxml={junit}", "-q"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
    )
    stop_ev.set()
    cap.join(timeout=5)
    dur = round(time.time() - t0, 1)
    status, detail = "fail", ""
    try:
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        tests = int(suite.get("tests", 0))
        fails = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        if tests == 0:
            status = "none"
        elif fails == 0:
            status = "pass" if skipped == 0 else "skipped"
        else:
            status = "fail"
            tcnode = suite.find("testcase")
            fnode = tcnode.find("failure") if tcnode is not None else None
            detail = (fnode.get("message", "") if fnode is not None else "")[:300]
    except Exception as e:
        status = "pass" if proc.returncode == 0 else "fail"
        detail = f"(junit 파싱 실패: {e})"
    # GIF 합성(프레임 2장 이상) → 실패 시 단일 스크린샷(테스트 저장분/폴백)
    made_gif = _make_gif(run_id)
    has_shot = made_gif or os.path.exists(os.path.join(SHOTS, run_id + ".png")) or _capture(run_id)
    _update_run(run_id, status=status, duration=dur, has_gif=made_gif,
                ended=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                detail=detail, has_shot=has_shot)


@app.route("/api/shot/<run_id>")
def api_shot(run_id):
    if not _re.match(r"^[\w.\-]+$", run_id):
        abort(400)
    for ext in (".gif", ".png"):   # GIF 우선, 없으면 단일 스크린샷
        if os.path.exists(os.path.join(SHOTS, run_id + ext)):
            return send_from_directory(SHOTS, run_id + ext)
    abort(404)


@app.route("/api/run/<tc>", methods=["POST"])
def api_run(tc):
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S_") + tc
    rec = {"id": run_id, "tc": tc, "status": "running", "duration": None,
           "started": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "ended": None, "detail": "", "has_shot": False, "has_gif": False}
    with _lock:
        items = _load_history()
        items.append(rec)
        _save_history(items)
    threading.Thread(target=_run_worker, args=(run_id, tc), daemon=True).start()
    return jsonify({"ok": True, "run": rec})


def _lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    # 같은 Wi-Fi(LAN)에서 접속 가능하도록 0.0.0.0 바인딩 (외부 인터넷 노출 아님)
    host = os.environ.get("PLUSRUN_HOST", "0.0.0.0")
    port = int(os.environ.get("PLUSRUN_PORT", "5050"))  # 5000은 macOS AirPlay가 점유
    ip = _lan_ip()
    print("=" * 56)
    print(" PLUS RUN 테스트 대시보드")
    print(f"  이 컴퓨터:      http://127.0.0.1:{port}")
    print(f"  같은 Wi-Fi 접속: http://{ip}:{port}   ← 이 링크를 공유하세요")
    print("  (같은 네트워크에 연결된 사람만 접속 가능 / 외부 인터넷 불가)")
    print("=" * 56)
    app.run(host=host, port=port, debug=False, threaded=True)
