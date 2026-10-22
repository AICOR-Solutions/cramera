"""
The browser files the viewer serves for the scene builder.
"""

from __future__ import annotations

from cramera.http.messages import HttpMethod, Request
from cramera_protocol.scene_builder import SceneBuilderFile, SceneBuilderName
from cramera_protocol.viewer import ViewerRoute
from cramera_scene_builder.plugin import WEB_DIRECTORY

from .conftest import HEADERS


def test_the_plugin_names_its_module(plugin):
    assert plugin.info().module == (
        f"{ViewerRoute.PLUGIN_FILES}{SceneBuilderName.PLUGIN}/{SceneBuilderFile.MODULE}"
    )


def test_the_module_and_the_page_are_served_below_the_plugin(answerer):
    for file in SceneBuilderFile:
        answer = answerer.answer(
            Request(
                method=HttpMethod.GET,
                path=f"{ViewerRoute.PLUGIN_FILES}{SceneBuilderName.PLUGIN}/{file}",
                headers=HEADERS,
            )
        )
        assert answer.body == (WEB_DIRECTORY / file).read_bytes()
