"""엑셀 테스트케이스 로더.

data/testcases.xlsx 의 'cases' 시트를 읽어 TC 별로 스텝을 묶는다.
같은 TC 값을 가진 연속/비연속 행들이 하나의 테스트 케이스가 된다.
행을 추가하면(새 TC) 자동으로 테스트가 늘어난다 → pytest.parametrize 로 연결.
"""
import os
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_XLSX = os.path.join(ROOT, "data", "testcases.xlsx")


def load_cases(path=DEFAULT_XLSX, sheet="cases"):
    """→ [(tc_id, name, [ (action, target), ... ]), ...] 정의 순서 유지."""
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    order, cases = [], {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # 헤더
        def g(j):
            return "" if j >= len(row) or row[j] is None else str(row[j]).strip()
        tc, name, action, target = g(0), g(1), g(2), g(3)
        if not tc or not action:
            continue
        if tc not in cases:
            cases[tc] = {"name": "", "steps": []}
            order.append(tc)
        if name:
            cases[tc]["name"] = name
        cases[tc]["steps"].append((action, target))
    return [(tc, cases[tc]["name"], cases[tc]["steps"]) for tc in order]
