"""
The cramera command's configuration and screenshot command.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import urllib.request
from http import HTTPStatus

import pytest

from cramera import screenshot
from cramera.command_line import DEFAULT_PORT, Option, ViewerConfiguration
from cramera.http.messages import HttpMethod
from cramera.scenes import SceneSource
from cramera.screenshot import (
    BrowserKind,
    PageReport,
    Screenshot,
    WebDriver,
    WebDriverKey,
)
from cramera_protocol.events import PageReportKey, PageState
from cramera_protocol.viewer import EnvironmentVariable, ViewerRoute

from .conftest import DATASET
from .dataset.webdriver import PNG_SIGNATURE, MimicWebDriver


def test_the_configuration_defaults_to_a_local_viewer(locations):
    configuration = ViewerConfiguration.from_arguments([], locations)
    assert (configuration.host, configuration.port, configuration.open_browser) == (
        "127.0.0.1",
        DEFAULT_PORT,
        True,
    )


def test_the_configuration_reads_every_option(locations, tmp_path):
    configuration = ViewerConfiguration.from_arguments(
        [
            Option.PORT,
            "9000",
            Option.SCENES,
            str(tmp_path / "a"),
            Option.DEMO_SCENES,
            str(tmp_path / "d"),
            Option.NO_BROWSER,
        ],
        locations,
    )
    sources = [directory.source for directory in configuration.scene_directories()]
    assert sources == [
        SceneSource.LOCAL,
        SceneSource.SHARED,
        SceneSource.SHARED,
        SceneSource.DEMO,
    ]
    assert configuration.port == 9000 and not configuration.open_browser


def test_the_configured_server_serves_the_viewer(locations):
    configuration = ViewerConfiguration(locations=locations, port=0, open_browser=False)
    with configuration.server() as server:
        assert server.bound_port() > 0


# %% screenshots


def test_browser_capabilities_ask_for_a_headless_window_of_the_given_size():
    for kind in BrowserKind:
        capabilities = kind.capabilities(800, 600)
        assert capabilities[WebDriverKey.BROWSER_NAME] == kind.value
        assert any(
            "800" in argument
            for options in capabilities.values()
            if isinstance(options, dict)
            for argument in options[WebDriverKey.ARGUMENTS]
        )


def test_a_screenshot_waits_until_the_page_is_ready(tmp_path):
    mimic = MimicWebDriver(states=[None, PageState.LOADING, PageState.READY])
    driver = WebDriver(BrowserKind.CHROME, port=mimic.start())
    output = tmp_path / "shots" / "viewer.png"
    report = Screenshot(url="http://localhost/", output=output, settle=0).take(driver)
    mimic.stop()
    assert report == PageReport(state=PageState.READY, status=mimic.status)
    assert report.succeeded()
    assert output.read_bytes() == PNG_SIGNATURE
    assert mimic.calls()[f"{HttpMethod.POST} /session/mimic/execute/sync"] == 3


def test_a_screenshot_of_a_failed_page_reports_the_failure(tmp_path):
    mimic = MimicWebDriver(states=[PageState.FAILED], status="Scene failed")
    report = Screenshot(
        url="http://localhost/", output=tmp_path / "s.png", settle=0
    ).take(WebDriver(BrowserKind.FIREFOX, port=mimic.start()))
    mimic.stop()
    assert not report.succeeded()


def test_a_page_that_never_reports_runs_into_the_timeout(tmp_path):
    mimic = MimicWebDriver(states=[PageState.LOADING])
    report = Screenshot(
        url="http://localhost/", output=tmp_path / "s.png", timeout=0.6, settle=0
    ).take(WebDriver(BrowserKind.CHROME, port=mimic.start()))
    mimic.stop()
    assert report.state == PageState.LOADING


def test_the_command_writes_the_report_and_exits_by_the_page_state(
    tmp_path, monkeypatch
):
    mimic = MimicWebDriver(states=[PageState.READY])
    port = mimic.start()
    monkeypatch.setattr(
        WebDriver, "start", lambda self: setattr(self, "port", port) or self
    )
    monkeypatch.setattr(WebDriver, "stop", lambda self: None)
    monkeypatch.setattr(Screenshot, "settle", 0)
    report_file = tmp_path / "report.json"
    code = screenshot.main(
        ["http://localhost/", str(tmp_path / "s.png"), "--report", str(report_file)]
    )
    mimic.stop()
    assert code == 0
    report = json.loads(report_file.read_text())
    assert report[PageReportKey.STATE] == PageState.READY
    assert report[PageReportKey.BROWSER] == BrowserKind.CHROME


def test_a_missing_driver_program_is_reported(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(FileNotFoundError):
        WebDriver(BrowserKind.CHROME).start()


# %% processes


def test_a_driver_program_is_started_and_stopped(tmp_path, monkeypatch):
    program = tmp_path / BrowserKind.CHROME.driver_program()
    program.write_text(
        f"#!{sys.executable}\n"
        + (DATASET / "listening_driver.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    program.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    with WebDriver(BrowserKind.CHROME) as driver:
        assert driver.is_listening()
        process = driver.process
    assert process.returncode is not None
    assert driver.process is None
    driver.stop()


def test_a_driver_that_never_listens_times_out(tmp_path):
    driver = WebDriver(BrowserKind.CHROME, port=WebDriver.free_port())
    with pytest.raises(TimeoutError):
        driver.wait_until_ready(timeout=0.3)


def test_the_viewer_command_serves_until_terminated(tmp_path):
    environment = {**os.environ, EnvironmentVariable.DATA: str(tmp_path)}
    environment.pop("PYTHONPATH", None)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "cramera.command_line",
            Option.PORT,
            "0",
            Option.NO_BROWSER,
        ],
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    announced = process.stderr.readline()
    url = announced.strip().rsplit(" ", 1)[-1]
    with urllib.request.urlopen(url + ViewerRoute.INFO) as answer:
        assert answer.status == HTTPStatus.OK
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=20) == 0
