"""시뮬레이터 화면 시험 (SWR-015): 실제 브라우저로 입력을 보내고 표시를 확인한다."""
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

from childlock.web.api import create_app

pytestmark = [pytest.mark.swr("SWR-015")]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def base_url():
    """시험마다 새 애플리케이션을 별도 포트로 띄운다."""
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "서버가 시작되지 않았습니다"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def page(base_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(base_url)
        yield page
        browser.close()


def test_page_initially_shows_released_off_state(page: Page):
    expect(page.locator("#left")).to_have_text("좌: RELEASE")
    expect(page.locator("#right")).to_have_text("우: RELEASE")
    expect(page.locator("#state")).to_have_text("OFF")


def test_lock_command_updates_outputs_reason_and_event_table(page: Page):
    page.select_option("#side", "all")
    page.select_option("#action", "lock")
    page.click("#send")
    expect(page.locator("#left")).to_have_text("좌: LOCK")
    expect(page.locator("#right")).to_have_text("우: LOCK")
    expect(page.locator("#state")).to_have_text("NORMAL")
    expect(page.locator("#reason")).to_have_text("DRIVER_COMMAND")
    expect(page.locator("#events tr")).to_have_count(1)


def test_crash_confirmed_input_shows_release_with_reason(page: Page):
    page.select_option("#side", "all")
    page.select_option("#action", "lock")
    page.click("#send")
    page.select_option("#side", "")
    page.select_option("#crash", "CONFIRMED")
    page.click("#send")
    expect(page.locator("#left")).to_have_text("좌: RELEASE")
    expect(page.locator("#reason")).to_have_text("CRASH_CONFIRMED")
    expect(page.locator("#events tr")).to_have_count(2)


def test_invalid_input_shows_error_message_and_keeps_outputs(page: Page):
    page.fill("#speed", "500")
    page.click("#send")
    expect(page.locator("#msg")).to_contain_text("vehicle_speed_kph")
    expect(page.locator("#reason")).to_have_text("INPUT_INVALID")
    expect(page.locator("#validity")).to_contain_text('"speed":"INVALID"')


def test_stale_input_shows_degraded(page: Page):
    page.fill("#age", "300")
    page.click("#send")
    expect(page.locator("#state")).to_have_text("DEGRADED")
    expect(page.locator("#reason")).to_have_text("INPUT_STALE")


def test_tick_button_before_input_shows_no_input_error(page: Page):
    page.click("#tick")
    expect(page.locator("#msg")).to_contain_text("입력이 아직 없습니다")
