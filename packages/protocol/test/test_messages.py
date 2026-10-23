"""
The live and viewer information documents, and the browser module.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS, BrowserModule
from cramera_protocol.exceptions import UnsupportedProtocolVersion
from cramera_protocol.live import Capability, LiveInfo, LiveInfoKey
from cramera_protocol.page import PageLayout, PageParameter, PageStorageKey, Theme
from cramera_protocol.version import CURRENT_VERSION
from cramera_protocol.viewer import (
    BuildKey,
    BuildStamp,
    NavigationGroup,
    NavigationKey,
    PluginInfo,
    PluginKey,
    PluginNavigation,
    Serving,
    ViewerInfo,
    ViewerInfoKey,
)

# %% information documents


def test_live_information_round_trips():
    info = LiveInfo(publisher="cramera-bridge 1.0.0", capabilities=[Capability.PLAN])
    written = info.to_json()
    assert written[LiveInfoKey.PROTOCOL_VERSION] == CURRENT_VERSION.to_json()
    assert written[LiveInfoKey.CAPABILITIES] == [Capability.PLAN.value]
    assert LiveInfo.from_json(written) == info


def test_live_information_of_another_major_version_is_refused():
    with pytest.raises(UnsupportedProtocolVersion):
        LiveInfo.from_json(
            {LiveInfoKey.PROTOCOL_VERSION: "9.0", LiveInfoKey.PUBLISHER: "x"}
        )


def test_viewer_information_lists_plugins():
    info = ViewerInfo(
        version="1.0.0",
        plugins=[
            PluginInfo(
                name="laboratory",
                version="1.0.0",
                module="/plugins/laboratory/index.js",
            )
        ],
    )
    assert ViewerInfo.from_json(info.to_json()) == info
    assert info.to_json()[ViewerInfoKey.PLUGINS][0]["name"] == "laboratory"


def test_a_plugin_names_its_page_in_the_navigation():
    navigation = PluginNavigation(
        title="Plan Builder",
        group=NavigationGroup.BUILDER,
        page="/plugins/plan-builder/builder.html",
    )
    plugin = PluginInfo(name="plan-builder", version="1.0.0", navigation=navigation)
    written = plugin.to_json()
    assert written[PluginKey.NAVIGATION][NavigationKey.GROUP] == NavigationGroup.BUILDER
    assert PluginInfo.from_json(written) == plugin


def test_a_navigation_entry_without_a_page_opens_the_plugins_panel():
    navigation = PluginNavigation(title="Workshop", group=NavigationGroup.LABORATORY)
    assert NavigationKey.PAGE not in navigation.to_json()
    assert PluginInfo(name="workshop", version="1.0.0").navigation is None


def test_a_viewer_is_served_by_its_server_unless_it_says_otherwise():
    assert ViewerInfo(version="1.0.0").serving == Serving.SERVER
    written = ViewerInfo(version="1.0.0", serving=Serving.STATIC).to_json()
    assert written[ViewerInfoKey.SERVING] == Serving.STATIC
    assert ViewerInfo.from_json(written).serving == Serving.STATIC


# %% browser module


def test_the_browser_module_exports_every_member():
    source = BrowserModule().source()
    for enumeration in BROWSER_ENUMERATIONS:
        exported = re.search(
            rf"export const {enumeration.__name__} = Object\.freeze\((.*?)\);",
            source,
            re.S,
        )
        assert json.loads(exported.group(1)) == {
            member.name: member.value for member in enumeration
        }


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_the_browser_module_imports_in_node(tmp_path):
    module = tmp_path / "protocol.mjs"
    module.write_text(BrowserModule().source(), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            f"import {{ PROTOCOL_VERSION }} from {json.dumps(module.as_uri())}; console.log(PROTOCOL_VERSION);",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == CURRENT_VERSION.to_json()


def test_a_published_build_names_its_commit_and_time():
    info = ViewerInfo(
        version="1.0.0",
        build=BuildStamp(commit="0" * 40, built_at="2026-10-22T13:00:00Z"),
    )
    written = info.to_json()
    assert written[ViewerInfoKey.BUILD][BuildKey.COMMIT] == "0" * 40
    assert ViewerInfo.from_json(written) == info
    assert ViewerInfoKey.BUILD not in ViewerInfo(version="1.0.0").to_json()


def test_the_page_names_are_offered_to_the_browser():
    for enumeration in (PageParameter, PageLayout, Theme, PageStorageKey):
        assert enumeration in BROWSER_ENUMERATIONS
