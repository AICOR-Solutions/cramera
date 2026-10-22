"""
``cramera-shot``: a screenshot of a viewer page in a headless browser, taken once the
page reports that its scene is ready.

The browser is driven through the WebDriver HTTP protocol, so only a driver program
(geckodriver or chromedriver) is needed besides the standard library.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import Any, Dict, Optional, Sequence

from cramera.http.messages import HttpMethod
from cramera_protocol.events import PageState, PageStateAttribute

# %% page state


class ReportKey(StrEnum):
    """
    The keys of the page report the state script returns and the command writes.
    """

    STATE = "state"
    """
    The page state.
    """

    STATUS = "status"
    """
    The status line.
    """


PAGE_STATE_SCRIPT = (
    "const data = document.documentElement.dataset;"
    f"return {{{ReportKey.STATE}: data.{PageStateAttribute.STATE} || null,"
    f" {ReportKey.STATUS}: data.{PageStateAttribute.STATUS} || null}};"
)
"""
The script reading the page's state and status line.
"""


@dataclass(frozen=True)
class PageReport:
    """
    What the page reported when the screenshot was taken.
    """

    state: Optional[str]
    """
    The page state, or None when the page never reported one.
    """

    status: Optional[str]
    """
    The page's status line.
    """

    def succeeded(self) -> bool:
        """
        :return: Whether the page showed its scene.
        """
        return self.state == PageState.READY


# %% browsers


class BrowserKind(StrEnum):
    """
    The browsers a screenshot can be taken in.
    """

    FIREFOX = "firefox"
    """
    Firefox through geckodriver.
    """

    CHROME = "chrome"
    """
    Chrome or Chromium through chromedriver.
    """

    def driver_program(self) -> str:
        """
        :return: The name of the WebDriver program of this browser.
        """
        return {BrowserKind.FIREFOX: "geckodriver", BrowserKind.CHROME: "chromedriver"}[
            self
        ]

    def capabilities(self, width: int, height: int) -> Dict[str, Any]:
        """
        :param width: The window width in pixels.
        :param height: The window height in pixels.
        :return: The WebDriver capabilities of a headless window with WebGL.
        """
        if self is BrowserKind.FIREFOX:
            options = {
                WebDriverKey.ARGUMENTS: [
                    "-headless",
                    f"--width={width}",
                    f"--height={height}",
                ],
                WebDriverKey.PREFERENCES: {
                    "webgl.force-enabled": True,
                    "webgl.disabled": False,
                },
            }
            return {
                WebDriverKey.BROWSER_NAME: self.value,
                WebDriverKey.FIREFOX_OPTIONS: options,
            }
        options = {
            WebDriverKey.ARGUMENTS: [
                "--headless=new",
                f"--window-size={width},{height}",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--no-sandbox",
            ]
        }
        return {
            WebDriverKey.BROWSER_NAME: self.value,
            WebDriverKey.CHROME_OPTIONS: options,
        }


# %% WebDriver


class WebDriverKey(StrEnum):
    """
    The keys of WebDriver requests and answers.
    """

    VALUE = "value"
    """
    The payload of every answer.
    """

    SESSION_IDENTIFIER = "sessionId"
    """
    The identity of a new session.
    """

    CAPABILITIES = "capabilities"
    """
    The requested browser features of a new session.
    """

    ALWAYS_MATCH = "alwaysMatch"
    """
    Capabilities every matching browser must have.
    """

    URL = "url"
    """
    The page to load.
    """

    SCRIPT = "script"
    """
    A script to run in the page.
    """

    ARGUMENTS = "args"
    """
    The arguments of a script or of a browser program.
    """

    BROWSER_NAME = "browserName"
    """
    The browser a session runs.
    """

    FIREFOX_OPTIONS = "moz:firefoxOptions"
    """
    Firefox's own session options.
    """

    CHROME_OPTIONS = "goog:chromeOptions"
    """
    Chrome's own session options.
    """

    PREFERENCES = "prefs"
    """
    Firefox preferences of a session.
    """


@dataclass(frozen=True)
class WebDriverEndpoint:
    """
    The WebDriver endpoints a screenshot uses.
    """

    session: Optional[str] = None
    """
    The session the endpoints act on, None for creating one.
    """

    def new_session(self) -> str:
        """
        :return: The endpoint that creates a session.
        """
        return "/session"

    def page(self) -> str:
        """
        :return: The endpoint that loads a page.
        """
        return f"/session/{self.session}/url"

    def script(self) -> str:
        """
        :return: The endpoint that runs a script synchronously.
        """
        return f"/session/{self.session}/execute/sync"

    def screenshot(self) -> str:
        """
        :return: The endpoint that captures the window.
        """
        return f"/session/{self.session}/screenshot"

    def end(self) -> str:
        """
        :return: The endpoint that closes the session.
        """
        return f"/session/{self.session}"


@dataclass
class WebDriver:
    """
    A WebDriver program listening on a local port, started by this object.
    """

    kind: BrowserKind
    """
    The browser the driver controls.
    """

    port: int = 0
    """
    The port the driver listens on; 0 picks a free port.
    """

    process: Optional[subprocess.Popen] = field(default=None, init=False)
    """
    The driver process while started.
    """

    def start(self) -> WebDriver:
        """
        Start the driver and wait until it accepts sessions.

        :return: This driver.
        :raises FileNotFoundError: When the driver program is not installed.
        """
        program = shutil.which(self.kind.driver_program())
        if program is None:
            raise FileNotFoundError(self.kind.driver_program())
        if self.port == 0:
            self.port = self.free_port()
        self.process = subprocess.Popen(
            [program, f"--port={self.port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.wait_until_ready()
        return self

    @staticmethod
    def free_port() -> int:
        """
        :return: A port no program listens on right now.
        """
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def wait_until_ready(self, timeout: float = 20.0) -> None:
        """
        :param timeout: How long to wait in seconds.
        :raises TimeoutError: When the driver does not get ready in time.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_listening():
                return
            time.sleep(0.2)
        raise TimeoutError(f"{self.kind.driver_program()} did not start")

    def is_listening(self) -> bool:
        """
        :return: Whether the driver's port accepts connections.
        """
        with socket.socket() as probe:
            return probe.connect_ex(("127.0.0.1", self.port)) == 0

    def call(
        self, method: HttpMethod, path: str, body: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        :param method: The HTTP method.
        :param path: The WebDriver endpoint.
        :param body: The JSON body, if any.
        :return: The ``value`` of the driver's answer.
        """
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            method=method.value,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=300) as answer:
            return json.loads(answer.read())[WebDriverKey.VALUE]

    def stop(self) -> None:
        """
        Stop the driver.
        """
        if self.process is None:
            return
        self.process.terminate()
        self.process.wait(timeout=20)
        self.process = None

    def __enter__(self) -> WebDriver:
        return self.start()

    def __exit__(self, *exception: object) -> None:
        self.stop()


# %% screenshot


@dataclass(frozen=True)
class Screenshot:
    """
    One screenshot of a viewer page.
    """

    url: str
    """
    The page.
    """

    output: Path
    """
    The PNG file to write.
    """

    width: int = 1600
    """
    The window width in pixels.
    """

    height: int = 1000
    """
    The window height in pixels.
    """

    timeout: float = 120.0
    """
    How long to wait for the page to report a final state, in seconds.
    """

    settle: float = 2.0
    """
    How long to let the ready page render before the screenshot, in seconds.
    """

    def take(self, driver: WebDriver) -> PageReport:
        """
        Load the page, wait until it reports ready or failed, and save the screenshot.

        :param driver: A started driver.
        :return: What the page reported.
        """
        capabilities = {
            WebDriverKey.CAPABILITIES: {
                WebDriverKey.ALWAYS_MATCH: driver.kind.capabilities(
                    self.width, self.height
                )
            }
        }
        created = driver.call(
            HttpMethod.POST, WebDriverEndpoint().new_session(), capabilities
        )
        endpoint = WebDriverEndpoint(created[WebDriverKey.SESSION_IDENTIFIER])
        try:
            driver.call(HttpMethod.POST, endpoint.page(), {WebDriverKey.URL: self.url})
            report = self.wait_for_final_state(driver, endpoint)
            time.sleep(self.settle)
            image = driver.call(HttpMethod.GET, endpoint.screenshot())
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.output.write_bytes(base64.b64decode(image))
        finally:
            driver.call(HttpMethod.DELETE, endpoint.end())
        return report

    def wait_for_final_state(
        self, driver: WebDriver, endpoint: WebDriverEndpoint
    ) -> PageReport:
        """
        :param driver: A started driver.
        :param endpoint: The endpoints of the session showing the page.
        :return: The page's report once it is ready or failed, or the last report
            when the timeout passes.
        """
        deadline = time.monotonic() + self.timeout
        report = PageReport(state=None, status=None)
        while time.monotonic() < deadline:
            values = driver.call(
                HttpMethod.POST,
                endpoint.script(),
                {WebDriverKey.SCRIPT: PAGE_STATE_SCRIPT, WebDriverKey.ARGUMENTS: []},
            )
            report = PageReport(
                state=values[ReportKey.STATE], status=values[ReportKey.STATUS]
            )
            if report.state in (PageState.READY, PageState.FAILED):
                return report
            time.sleep(0.5)
        return report


def main(arguments: Optional[Sequence[str]] = None) -> int:
    """
    Take a screenshot of a viewer page.

    :param arguments: The command-line arguments; the process arguments when None.
    :return: 0 when the page showed its scene, 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="cramera-shot", description=__doc__.strip().splitlines()[0]
    )
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--browser",
        type=BrowserKind,
        default=BrowserKind.CHROME,
        choices=list(BrowserKind),
    )
    parser.add_argument(
        "--size", nargs=2, type=int, default=(1600, 1000), metavar=("WIDTH", "HEIGHT")
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--report", type=Path, default=None, help="also write the page report as JSON"
    )
    parsed = parser.parse_args(arguments)
    screenshot = Screenshot(
        url=parsed.url,
        output=parsed.output,
        width=parsed.size[0],
        height=parsed.size[1],
        timeout=parsed.timeout,
    )
    with WebDriver(parsed.browser) as driver:
        report = screenshot.take(driver)
    if parsed.report is not None:
        parsed.report.write_text(
            json.dumps(
                {ReportKey.STATE: report.state, ReportKey.STATUS: report.status},
                indent=1,
            )
        )
    print(f"cramera-shot: {report.state} ({report.status}), saved {parsed.output}")
    return 0 if report.succeeded() else 1


if __name__ == "__main__":
    sys.exit(main())
