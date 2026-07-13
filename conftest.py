"""pytest 공통 설정 — Appium 드라이버 fixture, 설정 로딩, 스크린샷 헬퍼."""
import os
import time
import subprocess
import datetime as dt

import pytest
import yaml
from appium import webdriver
from appium.options.android import UiAutomator2Options

ROOT = os.path.dirname(os.path.abspath(__file__))
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")


def _load_config():
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # 환경변수 override (PLUSRUN_DEVICE / PLUSRUN_EMAIL / PLUSRUN_SPEED)
    cfg["device"] = os.environ.get("PLUSRUN_DEVICE", cfg["device"])
    cfg["login_email"] = os.environ.get("PLUSRUN_EMAIL", cfg["login_email"])
    cfg["speed"] = float(os.environ.get("PLUSRUN_SPEED", cfg["speed"]))
    return cfg


@pytest.fixture(scope="session")
def config():
    return _load_config()


@pytest.fixture(scope="session")
def artifacts_dir():
    d = os.path.join(ROOT, "artifacts", dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture
def driver(config):
    o = UiAutomator2Options()
    o.platform_name = "Android"
    o.device_name = config["device"]
    o.udid = config["device"]
    o.app_package = config["app_package"]
    o.app_activity = config["app_activity"]
    o.no_reset = True
    o.full_reset = False
    o.new_command_timeout = 2000
    o.set_capability("appium:forceAppLaunch", True)
    o.set_capability("appium:shouldTerminateApp", True)
    o.set_capability("appium:appWaitActivity", "*")
    o.set_capability("appium:autoGrantPermissions", True)
    # 디버그 빌드 카카오 우회 로그인
    o.set_capability("appium:optionalIntentArguments",
                     f"--es e2e_login_email {config['login_email']}")
    drv = webdriver.Remote(config["appium_url"], options=o)
    yield drv
    try:
        drv.quit()
    except Exception:
        pass


def adb(device, *args):
    subprocess.run([ADB, "-s", device, *args], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def shot(driver, artifacts_dir, name):
    try:
        driver.save_screenshot(os.path.join(artifacts_dir, name))
    except Exception:
        pass
