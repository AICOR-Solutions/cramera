"""
The screenshot an export takes of its published bundle, through the viewer.
"""

from __future__ import annotations

import urllib.parse

import pytest

pytest.importorskip("cramera.screenshot")

from cramera.screenshot import Screenshot
from cramera_protocol.events import PageState
from cramera_protocol.page import PageParameter
from cramera_usd.export.screenshot import ViewerScreenshot

from .dataset.webdriver import PNG_SIGNATURE, READY_STATUS, MimicWebDriver

# %% page address


def test_the_page_opens_the_published_bundle(tmp_path):
    shot = ViewerScreenshot(tmp_path, "cell", tmp_path / "cell.png")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(shot.page("http://host")).query)
    assert query == {PageParameter.SCENE.value: ["cell"]}


# %% screenshot


def test_the_screenshot_is_taken_from_the_served_page(tmp_path, monkeypatch):
    monkeypatch.setattr(Screenshot, "settle", 0)
    driver = MimicWebDriver()
    output = tmp_path / "cell.png"
    report = ViewerScreenshot(tmp_path, "cell", output).take(lambda: driver)
    assert (report.state, report.status) == (PageState.READY, READY_STATUS)
    assert output.read_bytes() == PNG_SIGNATURE
    (page,) = driver.pages
    assert page.startswith("http://127.0.0.1:")
