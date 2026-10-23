"""
The questions plugin in a viewer installation without krrood.
"""

from __future__ import annotations

import json
import subprocess
import sys
from http import HTTPStatus
from importlib.machinery import ModuleSpec

import pytest

from cramera.application import ViewerApplication
from cramera.http.messages import Header, HttpMethod, Request
from cramera.http.origin import OriginPolicy
from cramera.http.server import RequestAnswerer
from cramera.locations import DataLocations
from cramera_protocol.plugins import PluginName
from cramera_protocol.questions import QuestionsRoute
from cramera_protocol.viewer import ErrorKey, ViewerRoute
from cramera_questions.exceptions import QueryLanguageMissing
from cramera_questions.plugin import QueryLanguageInstallation, QuestionsPlugin
from cramera_questions.workspace_classes import WorkspaceClassIndex, WorkspacePackage

from .dataset.files import IMPORT_PLUGIN_WITHOUT_KRROOD

LOCAL_HOST = {Header.HOST: "127.0.0.1:8711"}
"""
The headers of a request addressed to this machine.
"""


@pytest.fixture
def answerer(catalog, tmp_path) -> RequestAnswerer:
    """
    :return: The viewer's request answerer with a plugin that finds no krrood.
    """
    plugin = QuestionsPlugin(
        class_index=WorkspaceClassIndex(),
        installation=QueryLanguageInstallation(finder=lambda name: None),
    )
    application = ViewerApplication(
        catalog=catalog,
        locations=DataLocations(data=tmp_path / "data", shared_scenes=None),
        plugins=[plugin],
    )
    return RequestAnswerer(router=application.router(), policy=OriginPolicy())


def test_the_plugin_imports_without_krrood():
    result = subprocess.run(
        [sys.executable, str(IMPORT_PLUGIN_WITHOUT_KRROOD)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == PluginName.QUESTIONS.value


@pytest.mark.parametrize("method", [HttpMethod.GET, HttpMethod.POST])
@pytest.mark.parametrize("plugin_route", list(QuestionsRoute))
def test_every_route_answers_that_krrood_is_missing(answerer, method, plugin_route):
    response = answerer.answer(
        Request(
            method=method,
            path=f"{ViewerRoute.PLUGIN_API}{PluginName.QUESTIONS}/{plugin_route}",
            headers=LOCAL_HOST,
        )
    )
    assert response.status is HTTPStatus.SERVICE_UNAVAILABLE
    assert (
        json.loads(response.body)[ErrorKey.ERROR]
        == QueryLanguageMissing(WorkspacePackage.KRROOD.value).message()
    )


def test_the_plugin_still_offers_its_browser_module():
    info = QuestionsPlugin(class_index=WorkspaceClassIndex()).info()
    assert info.module == f"{ViewerRoute.PLUGIN_FILES}{PluginName.QUESTIONS}/index.js"


def test_a_directory_named_like_krrood_is_no_installation():
    namespace = ModuleSpec(WorkspacePackage.KRROOD.value, loader=None)
    installation = QueryLanguageInstallation(finder=lambda name: namespace)
    assert not installation.is_installed()
