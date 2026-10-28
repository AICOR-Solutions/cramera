"""
The plugin's routes in the viewer: what this machine and the pages behind the proxy may
ask.
"""

from __future__ import annotations

import json
import time
from http import HTTPStatus

import pytest

from cramera.application import ViewerApplication
from cramera.http.messages import Header, HttpMethod, Request
from cramera.http.origin import LOCAL_HOSTS, OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera.scenes import SceneCatalog, SceneDirectory, SceneSource
from cramera_protocol.scene_runs import (
    SceneRunsName,
    SceneRunsRoute,
    SceneRunsState,
    SceneRunState,
    SceneRunsVariable,
)
from cramera_protocol.viewer import ErrorKey, ViewerRoute
from cramera_scene_runs.exceptions import InvalidSceneRunCatalog
from cramera_scene_runs.plugin import WEB_DIRECTORY, SceneRunsPlugin

PREFIX = f"{ViewerRoute.PLUGIN_API}{SceneRunsName.PLUGIN}/"
"""
The plugin's routes.
"""

PUBLIC_HOST = "cramera.example.org"
"""
The host name the proxy serves the viewer at.
"""


@pytest.fixture
def plugin(catalog, tmp_path):
    """
    :return: The plugin, offering the catalog's runs from its file.
    """
    path = tmp_path / "runs.json"
    path.write_text(json.dumps(catalog.to_json()), encoding="utf-8")
    plugin = SceneRunsPlugin(environment={SceneRunsVariable.CATALOG: str(path)})
    yield plugin
    plugin.close()


def viewer(plugin, scenes, tmp_path, policy) -> RequestAnswerer:
    """
    :return: The viewer with the plugin, whose local scenes are the runs' scenes.
    """
    application = ViewerApplication(
        catalog=SceneCatalog([SceneDirectory(scenes, SceneSource.LOCAL)]),
        locations=DataLocations(data=tmp_path / "data", shared_scenes=None),
        plugins=[plugin],
    )
    return RequestAnswerer(router=application.router(), policy=policy)


def proxied(method: HttpMethod, route: str) -> Request:
    """
    :return: A request a page behind the proxy sends.
    """
    return Request(
        method=method,
        path=f"{PREFIX}{route}",
        headers={Header.HOST: PUBLIC_HOST, Header.ORIGIN: f"https://{PUBLIC_HOST}"},
    )


PROXY_POLICY = OriginPolicy(allowed_hosts=LOCAL_HOSTS | {PUBLIC_HOST}, proxied=True)
"""
The policy of a viewer behind a password-checking proxy.
"""


def state_of(answer) -> SceneRunsState:
    assert answer.status is HTTPStatus.OK, answer.body
    return SceneRunsState.from_json(json.loads(answer.body))


def test_the_plugin_offers_its_panel_where_the_server_offers_runs(plugin):
    info = plugin.info()
    assert info.name == SceneRunsName.PLUGIN
    assert info.module == f"{ViewerRoute.PLUGIN_FILES}{SceneRunsName.PLUGIN}/index.js"
    assert (WEB_DIRECTORY / "index.js").is_file()


def test_without_a_catalog_file_the_plugin_adds_no_panel():
    assert SceneRunsPlugin(environment={}).info().module is None


def test_without_a_catalog_file_nothing_is_offered(scenes, tmp_path):
    answerer = viewer(SceneRunsPlugin(environment={}), scenes, tmp_path, OriginPolicy())
    answer = answerer.answer(
        Request(
            method=HttpMethod.GET,
            path=f"{PREFIX}{SceneRunsRoute.STATE}",
            headers={Header.HOST: "localhost"},
        )
    )
    assert state_of(answer).runs == []


def test_a_catalog_file_the_viewer_cannot_offer_stops_the_viewer(scenes, tmp_path):
    path = tmp_path / "runs.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(InvalidSceneRunCatalog):
        viewer(
            SceneRunsPlugin(environment={SceneRunsVariable.CATALOG: str(path)}),
            scenes,
            tmp_path,
            OriginPolicy(),
        )


def test_a_page_behind_the_proxy_starts_watches_and_stops_a_run(
    plugin, scenes, tmp_path
):
    answerer = viewer(plugin, scenes, tmp_path, PROXY_POLICY)
    started = state_of(
        answerer.answer(
            proxied(HttpMethod.POST, f"{SceneRunsRoute.START}garmi_apartment")
        )
    )
    assert started.current.state is SceneRunState.RUNNING
    state = state_of(answerer.answer(proxied(HttpMethod.GET, SceneRunsRoute.STATE)))
    assert state.current.identifier == "garmi_apartment"
    busy = answerer.answer(
        proxied(HttpMethod.POST, f"{SceneRunsRoute.START}pr2_transfer")
    )
    assert busy.status is HTTPStatus.CONFLICT
    assert ErrorKey.ERROR in json.loads(busy.body)
    stopped = state_of(answerer.answer(proxied(HttpMethod.POST, SceneRunsRoute.STOP)))
    assert stopped.current.state is SceneRunState.STOPPED


def test_a_recorded_run_is_found_in_the_viewer_s_scenes(plugin, scenes, tmp_path):
    answerer = viewer(plugin, scenes, tmp_path, PROXY_POLICY)
    answerer.answer(proxied(HttpMethod.POST, f"{SceneRunsRoute.START}pr2_transfer"))
    deadline = time.monotonic() + 20
    state = state_of(answerer.answer(proxied(HttpMethod.GET, SceneRunsRoute.STATE)))
    while state.current.state is SceneRunState.RUNNING:
        assert time.monotonic() < deadline
        time.sleep(0.05)
        state = state_of(answerer.answer(proxied(HttpMethod.GET, SceneRunsRoute.STATE)))
    assert state.current.state is SceneRunState.RECORDED
    assert (tmp_path / "data" / "scene-runs").is_dir()


def test_a_phone_of_the_network_does_not_start_runs(plugin, scenes, tmp_path):
    answerer = viewer(plugin, scenes, tmp_path, OriginPolicy(key="k"))
    request = Request(
        method=HttpMethod.POST,
        path=f"{PREFIX}{SceneRunsRoute.START}pr2_transfer",
        headers={Header.HOST: "192.0.2.7:8711", Header.COOKIE: "cramera_key=k"},
        server_address="192.0.2.7",
        client_address="192.0.2.50",
    )
    assert answerer.answer(request).status is HTTPStatus.FORBIDDEN
