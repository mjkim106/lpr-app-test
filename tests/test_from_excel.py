"""엑셀 케이스 데이터 주도 테스트.

data/testcases.xlsx 의 각 TC 를 pytest 케이스로 자동 생성한다.
엑셀에 TC 를 추가하면(4번, 5번...) 코드 수정 없이 테스트가 늘어난다.

실행: (Appium 서버 기동 후)  pytest tests/test_from_excel.py -v
      특정 케이스만:          pytest tests/test_from_excel.py -k TC1
"""
import os

import pytest

from conftest import shot, ADB
from lib.excel_cases import load_cases
from lib.keywords import KeywordRunner

CASES = load_cases()  # [(tc_id, name, steps), ...]


@pytest.mark.parametrize(
    "tc_id,name,steps",
    CASES,
    ids=[f"{tc}-{name}" for tc, name, _ in CASES],
)
def test_excel_case(driver, config, artifacts_dir, tc_id, name, steps):
    runner = KeywordRunner(driver, config, ADB)
    try:
        for idx, (action, target) in enumerate(steps):
            runner.run_step(action, target)
    finally:
        shot(driver, artifacts_dir, f"{tc_id}.png")
