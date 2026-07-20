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

from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import casestore              # noqa: E402
from lib.keywords import ACTIONS       # noqa: E402

XLSX = os.path.join(ROOT, "data", "testcases.xlsx")
HISTORY = os.path.join(ROOT, "data", "run_history.json")
ARTIFACTS = os.path.join(ROOT, "artifacts")
_lock = threading.Lock()

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
    return jsonify(ACTIONS)


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
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_from_excel.py",
         "-k", tc, f"--junitxml={junit}", "-q"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
    _update_run(run_id, status=status, duration=dur,
                ended=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), detail=detail)


@app.route("/api/run/<tc>", methods=["POST"])
def api_run(tc):
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S_") + tc
    rec = {"id": run_id, "tc": tc, "status": "running", "duration": None,
           "started": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "ended": None, "detail": ""}
    with _lock:
        items = _load_history()
        items.append(rec)
        _save_history(items)
    threading.Thread(target=_run_worker, args=(run_id, tc), daemon=True).start()
    return jsonify({"ok": True, "run": rec})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
