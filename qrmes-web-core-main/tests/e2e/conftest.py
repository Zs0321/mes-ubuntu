# tests/e2e/conftest.py
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pytest
from playwright.sync_api import sync_playwright
from tests.e2e.config import TEST_CONFIG
from tests.e2e.utils.console_monitor import ConsoleMonitor


def _resolve_browser_order():
    """确定 E2E 浏览器启动顺序。默认优先 Chromium（Firefox Nightly 在部分 macOS 上会崩溃）。"""
    default_order = ['chromium', 'firefox', 'webkit']
    preferred = os.getenv('PW_BROWSER', '').strip().lower()
    if preferred in default_order:
        return [preferred] + [name for name in default_order if name != preferred]
    return default_order


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        errors = []
        for browser_name in _resolve_browser_order():
            try:
                browser_type = getattr(p, browser_name)
                browser = browser_type.launch(headless=True)
                yield browser
                browser.close()
                return
            except Exception as exc:
                errors.append(f"{browser_name}: {exc}")

        pytest.fail("无法启动 Playwright 浏览器。尝试结果: " + " | ".join(errors))

@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()

    # 设置控制台监控
    monitor = ConsoleMonitor()
    page.on("console", monitor.on_console)
    page.monitor = monitor

    yield page

    # 如果测试失败,截图
    if hasattr(page, '_test_failed') and page._test_failed:
        screenshot_path = f"{TEST_CONFIG['screenshots_dir']}/{page._test_name}.png"
        page.screenshot(path=screenshot_path)

    context.close()

@pytest.fixture
def logged_in_page(page):
    """已登录的页面 fixture"""
    page.goto(f"{TEST_CONFIG['base_url']}/login")
    page.fill('input[name="username"]', TEST_CONFIG['test_user']['username'])
    page.fill('input[name="password"]', TEST_CONFIG['test_user']['password'])
    page.click('button[type="submit"]')
    page.wait_for_url(f"{TEST_CONFIG['base_url']}/")
    return page

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()

    if rep.when == "call" and rep.failed:
        if hasattr(item, 'funcargs') and 'page' in item.funcargs:
            page = item.funcargs['page']
            page._test_failed = True
            page._test_name = item.name
