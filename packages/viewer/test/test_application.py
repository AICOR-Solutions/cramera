"""
The viewer's routes and its plugins.
"""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest

from cramera.application import ViewerApplication
from cramera.exceptions import DuplicatePlugin, InvalidPluginName
from cramera.http.messages import Header, HttpMethod, MediaType, Request
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.plugins import PluginLoader
from cramera_protocol.browser import BrowserModule
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.live import Capability
from cramera_protocol.viewer import ViewerInfo, ViewerRoute

from .dataset.plugins import FactoryEntryPoint, QuestionPlugin, SilentPlugin

HEADERS = {Header.HOST: "localhost"}
"""
The headers of a request addressed to this machine.
"""


def get(answerer, path):
    return answerer.answer(Request(method=HttpMethod.GET, path=path, headers=HEADERS))


@pytest.fixture
def plugin():
    return QuestionPlugin()


@pytest.fixture
def plugged(catalog, locations, plugin, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (web / "app.js").write_text("export {};", encoding="utf-8")
    application = ViewerApplication(
        catalog=catalog,
        locations=locations,
        plugins=[plugin, SilentPlugin()],
        web_directory=web,
    )
    return RequestAnswerer(router=application.router(), policy=OriginPolicy())


def test_info_names_the_viewer_and_its_plugins(plugged):
    info = ViewerInfo.from_json(json.loads(get(plugged, ViewerRoute.INFO).body))
    assert [plugin.name for plugin in info.plugins] == ["questions", "silent"]
    assert info.plugins[0].module == f"{ViewerRoute.PLUGIN_FILES}questions/index.js"
    assert info.plugins[0].capabilities == [Capability.QUESTIONS]
    assert info.plugins[1].module is None


def test_the_scenes_route_answers_the_merged_index(plugged, catalog):
    index = SceneIndex.from_json(json.loads(get(plugged, ViewerRoute.SCENES).body))
    assert index == catalog.index()


def test_the_protocol_module_is_served_as_javascript(plugged):
    answer = get(plugged, ViewerRoute.PROTOCOL_MODULE)
    assert answer.media_type is MediaType.JAVASCRIPT
    assert answer.body.decode() == BrowserModule().source()


def test_bundle_files_are_served_with_their_media_type(plugged):
    answer = get(plugged, f"{ViewerRoute.SCENE_FILES}converted/{BundleFile.LIGHTING}")
    assert answer.status is HTTPStatus.OK
    assert answer.media_type is MediaType.JSON


def test_plugin_files_and_routes_are_served_below_the_plugin_name(
    plugged, plugin, catalog
):
    assert (
        get(plugged, f"{ViewerRoute.PLUGIN_FILES}questions/index.js").media_type
        is MediaType.JAVASCRIPT
    )
    assert (
        get(plugged, f"{ViewerRoute.PLUGIN_FILES}silent/index.js").status
        is HTTPStatus.NOT_FOUND
    )
    asked = plugged.answer(
        Request(
            method=HttpMethod.POST,
            path=f"{ViewerRoute.PLUGIN_API}questions/ask",
            headers=HEADERS,
            body=b'{"q": 1}',
        )
    )
    assert json.loads(asked.body) == {"echo": {"q": 1}}
    assert plugin.contexts[0].catalog is catalog


def test_a_plugin_prefix_route_answers_every_path_below_it(plugged):
    answer = get(plugged, f"{ViewerRoute.PLUGIN_API}questions/topics/robots/arms")
    assert json.loads(answer.body) == {"topic": "robots/arms"}
    assert (
        get(plugged, f"{ViewerRoute.PLUGIN_API}questions/topics").status
        is HTTPStatus.NOT_FOUND
    )


def test_the_page_and_its_files_are_served_last(plugged):
    assert get(plugged, "/").body == b"<!doctype html>"
    assert get(plugged, "/app.js").media_type is MediaType.JAVASCRIPT
    assert get(plugged, "/../secret").status is HTTPStatus.FORBIDDEN


def test_the_packaged_page_exists(answerer):
    assert get(answerer, "/").status is HTTPStatus.OK


# %% loading plugins


def test_plugins_are_loaded_from_entry_points_sorted_by_name():
    loader = PluginLoader(
        entry_points=[
            FactoryEntryPoint(SilentPlugin()),
            FactoryEntryPoint(QuestionPlugin()),
        ]
    )
    assert [plugin.name() for plugin in loader.load()] == ["questions", "silent"]


def test_installed_entry_points_are_read_by_default():
    assert isinstance(PluginLoader().load(), list)


@pytest.mark.parametrize("name", ["Questions", "with space", "-dash", "a/b", ""])
def test_a_plugin_name_that_is_no_route_segment_is_refused(name):
    with pytest.raises(InvalidPluginName):
        PluginLoader(
            entry_points=[FactoryEntryPoint(SilentPlugin(plugin_name=name))]
        ).load()


def test_two_plugins_with_one_name_are_refused():
    loader = PluginLoader(
        entry_points=[
            FactoryEntryPoint(SilentPlugin()),
            FactoryEntryPoint(SilentPlugin()),
        ]
    )
    with pytest.raises(DuplicatePlugin):
        loader.load()
