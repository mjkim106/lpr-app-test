"""액션 메타/코드 조회·CRUD.

- 내장 액션: lib.keywords.ACTIONS (메타) + KeywordRunner 메서드 소스(코드, 읽기전용)
- 사용자 액션: lib/custom_actions.py (코드, 마커 블록) + data/custom_actions.json (메타)
"""
import os
import re
import json
import inspect
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUSTOM_PY = os.path.join(ROOT, "lib", "custom_actions.py")
CUSTOM_JSON = os.path.join(ROOT, "data", "custom_actions.json")


# ---------- 사용자 액션 메타 ----------
def _load_meta():
    if os.path.exists(CUSTOM_JSON):
        try:
            with open(CUSTOM_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_meta(d):
    os.makedirs(os.path.dirname(CUSTOM_JSON), exist_ok=True)
    with open(CUSTOM_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


# ---------- 사용자 액션 코드(마커 블록) ----------
def _read_py():
    with open(CUSTOM_PY, encoding="utf-8") as f:
        return f.read()


def custom_code(name):
    txt = _read_py()
    m = re.search(rf"# === action: {re.escape(name)} ===\n(.*?)\n# === end: {re.escape(name)} ===",
                  txt, re.S)
    return m.group(1) if m else ""


def load_custom_funcs():
    """custom_actions.py 를 로드해 {name: func} 반환."""
    funcs = {}
    if not os.path.exists(CUSTOM_PY):
        return funcs
    spec = importlib.util.spec_from_file_location("custom_actions_dyn", CUSTOM_PY)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return funcs
    for n in dir(mod):
        f = getattr(mod, n)
        if callable(f) and not n.startswith("_") and getattr(f, "__module__", "") == "custom_actions_dyn":
            funcs[n] = f
    return funcs


# ---------- 목록(내장+사용자) ----------
def list_all():
    from lib.keywords import ACTIONS
    out = []
    for name, meta in ACTIONS.items():
        out.append({"name": name, "type": "builtin",
                    "desc": meta.get("desc", ""), "needs_target": meta.get("needs_target", True),
                    "target_hint": meta.get("target_hint", "")})
    meta = _load_meta()
    for name in load_custom_funcs():
        m = meta.get(name, {})
        out.append({"name": name, "type": "custom",
                    "desc": m.get("desc", ""), "needs_target": m.get("needs_target", True),
                    "target_hint": m.get("target_hint", "")})
    return out


def get_code(name):
    """내장은 KeywordRunner 메서드 소스, 사용자는 마커 블록 소스."""
    from lib.keywords import ACTIONS, KeywordRunner
    if name in ACTIONS:
        try:
            return {"type": "builtin", "code": inspect.getsource(getattr(KeywordRunner, name))}
        except Exception:
            return {"type": "builtin", "code": "(소스를 찾을 수 없습니다)"}
    if name in load_custom_funcs():
        return {"type": "custom", "code": custom_code(name)}
    return {"type": "none", "code": ""}


# ---------- 추가/수정/삭제(사용자 액션만) ----------
def _validate(name, code):
    from lib.keywords import ACTIONS
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise ValueError("액션 이름은 영문/숫자/밑줄만, 숫자로 시작 불가")
    if name in ACTIONS:
        raise ValueError(f"'{name}' 은 내장 액션이라 덮어쓸 수 없습니다")
    if f"def {name}(" not in code:
        raise ValueError(f"코드에 'def {name}(ctx, target):' 정의가 있어야 합니다")
    compile(code, "<custom>", "exec")  # 문법 검증


def upsert(name, code, desc="", needs_target=True, target_hint=""):
    _validate(name, code)
    txt = _read_py()
    block = (f"\n# === action: {name} ===\n{code.rstrip()}\n# === end: {name} ===\n")
    pat = rf"\n# === action: {re.escape(name)} ===\n.*?\n# === end: {re.escape(name)} ===\n"
    if re.search(pat, txt, re.S):
        txt = re.sub(pat, block, txt, flags=re.S)   # 수정
    else:
        txt = txt.rstrip() + "\n" + block            # 추가
    with open(CUSTOM_PY, "w", encoding="utf-8") as f:
        f.write(txt)
    meta = _load_meta()
    meta[name] = {"desc": desc, "needs_target": bool(needs_target), "target_hint": target_hint}
    _save_meta(meta)
    # 로드 검증
    if name not in load_custom_funcs():
        raise ValueError("코드는 저장됐지만 함수 로드에 실패했습니다. 시그니처를 확인하세요.")


def delete(name):
    from lib.keywords import ACTIONS
    if name in ACTIONS:
        raise ValueError("내장 액션은 삭제할 수 없습니다")
    txt = _read_py()
    pat = rf"\n# === action: {re.escape(name)} ===\n.*?\n# === end: {re.escape(name)} ===\n"
    txt = re.sub(pat, "\n", txt, flags=re.S)
    with open(CUSTOM_PY, "w", encoding="utf-8") as f:
        f.write(txt)
    meta = _load_meta()
    meta.pop(name, None)
    _save_meta(meta)
