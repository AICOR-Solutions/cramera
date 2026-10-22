"""
The offline plugin's routes and what it tells the viewer.
"""

from __future__ import annotations

import json
import shutil
from http import HTTPStatus
from importlib.metadata import entry_points

from cramera.plugins import PluginLoader
from cramera_offline.bundle_check import BundleCheck
from cramera_offline.plugin import OfflinePlugin, WebFile
from cramera_protocol.offline import (
    BundleCheckReport,
    OfflineParameter,
    OfflineRoute,
    PresentationFile,
    Storyboard,
)
from cramera_protocol.plugins import PluginName
from cramera_protocol.viewer import ErrorKey, PluginGroup, ViewerRoute

from .dataset.requests import answer_json, local_request

STORYBOARD_ROUTE = (
    f"{ViewerRoute.PLUGIN_API}{PluginName.OFFLINE}/{OfflineRoute.STORYBOARD}"
)
"""
Where the viewer serves the storyboard.
"""

BUNDLE_CHECK_ROUTE = (
    f"{ViewerRoute.PLUGIN_API}{PluginName.OFFLINE}/{OfflineRoute.BUNDLE_CHECK}"
)
"""
Where the viewer serves a bundle's completeness report.
"""

# %% plugin


def test_the_plugin_is_installed_under_its_protocol_name():
    installed = [
        entry_point
        for entry_point in entry_points(group=PluginGroup.VIEWER)
        if entry_point.name == PluginName.OFFLINE
    ]
    plugins = PluginLoader(entry_points=installed).load()
    assert [plugin.name() for plugin in plugins] == [PluginName.OFFLINE]


def test_the_plugin_names_its_browser_module():
    info = OfflinePlugin().info()
    assert info.name == PluginName.OFFLINE
    assert (
        info.module
        == f"{ViewerRoute.PLUGIN_FILES}{PluginName.OFFLINE}/{WebFile.MODULE}"
    )
    assert (OfflinePlugin().web_directory() / WebFile.MODULE).is_file()


def test_the_storyboard_route_is_where_the_viewer_serves_it():
    assert OfflinePlugin().storyboard_route() == STORYBOARD_ROUTE


# %% storyboard


def test_the_storyboard_of_a_scenes_directory_is_answered(
    answerer, recorded_scenes, storyboard_file
):
    shutil.copy(storyboard_file, recorded_scenes / PresentationFile.STORYBOARD)
    response = answerer.answer(local_request(STORYBOARD_ROUTE))
    assert response.status == HTTPStatus.OK
    expected = Storyboard.from_json(json.loads(storyboard_file.read_text()))
    assert Storyboard.from_json(answer_json(response)) == expected


def test_without_a_storyboard_the_answer_says_so(answerer, recorded_scenes):
    response = answerer.answer(local_request(STORYBOARD_ROUTE))
    assert response.status == HTTPStatus.NOT_FOUND
    assert str(recorded_scenes) in answer_json(response)[ErrorKey.ERROR]


def test_a_damaged_storyboard_is_answered_as_a_bad_request(
    answerer, recorded_scenes, dataset
):
    shutil.copy(
        dataset / "unreadable_storyboard.json",
        recorded_scenes / PresentationFile.STORYBOARD,
    )
    response = answerer.answer(local_request(STORYBOARD_ROUTE))
    assert response.status == HTTPStatus.BAD_REQUEST


# %% bundle check


def test_the_bundle_check_of_a_bundle_is_answered(answerer, broken_bundle):
    response = answerer.answer(
        local_request(
            BUNDLE_CHECK_ROUTE, f"{OfflineParameter.SCENE}={broken_bundle.name}"
        )
    )
    assert response.status == HTTPStatus.OK
    assert (
        BundleCheckReport.from_json(answer_json(response))
        == BundleCheck(broken_bundle).report()
    )


def test_a_bundle_check_without_a_scene_is_a_bad_request(answerer):
    response = answerer.answer(local_request(BUNDLE_CHECK_ROUTE))
    assert response.status == HTTPStatus.BAD_REQUEST
    assert OfflineParameter.SCENE in answer_json(response)[ErrorKey.ERROR]


def test_a_bundle_check_of_an_unknown_scene_is_not_found(answerer):
    response = answerer.answer(
        local_request(BUNDLE_CHECK_ROUTE, f"{OfflineParameter.SCENE}=never_recorded")
    )
    assert response.status == HTTPStatus.NOT_FOUND
