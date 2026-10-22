"""
Serving a presentation with the viewer: only its bundles, and pages confined to their
own origin.
"""

from __future__ import annotations

import json
import socket

import pytest

from cramera.http.server import HttpServer
from cramera_offline.isolation import InheritedSocketServer
from cramera_offline.plugin import OfflinePlugin
from cramera_offline.presentation import PresentationPreparation
from cramera_offline.presentation_command import LOOPBACK
from cramera_offline.presentation_server import (
    PresentationHeader,
    PresentationPolicy,
    PresentationServer,
)
from cramera_protocol.bundle.index import SceneIndex
from cramera_protocol.viewer import ViewerRoute

from .dataset.requests import local_request


@pytest.fixture
def presentation(tmp_path, recorded_scenes, storyboard_file):
    """
    :return: A presentation prepared from the storyboard of the complete bundle.
    """
    return PresentationPreparation(
        storyboard_file, [recorded_scenes], tmp_path / "presentation"
    ).prepare()


@pytest.fixture
def server(presentation) -> PresentationServer:
    """
    :return: The presentation's server with the offline plugin.
    """
    return PresentationServer(presentation, plugins=[OfflinePlugin()])


# %% answers


def test_only_the_presented_bundles_are_offered(server, presentation):
    response = server.answerer().answer(local_request(ViewerRoute.SCENES))
    index = SceneIndex.from_json(json.loads(response.body))
    assert [
        entry.name for entry in index.scenes
    ] == presentation.storyboard().scene_names()


def test_every_answer_carries_the_confining_headers(server):
    policy = PresentationPolicy()
    response = server.answerer().answer(local_request("/"))
    assert response.headers[PresentationHeader.CONTENT_SECURITY_POLICY] == (
        policy.content_security_policy
    )
    assert response.headers[PresentationHeader.PERMISSIONS_POLICY] == (
        policy.permissions_policy
    )


# %% servers


def test_without_a_descriptor_the_server_opens_its_own_socket(server):
    built = server.server(LOOPBACK, 0, None)
    assert type(built) is HttpServer
    assert (built.host, built.port) == (LOOPBACK, 0)


def test_with_a_descriptor_the_server_answers_on_the_inherited_socket(server):
    with socket.create_server((LOOPBACK, 0)) as listener:
        built = server.server(LOOPBACK, 0, listener.fileno())
        assert isinstance(built, InheritedSocketServer)
        assert built.descriptor == listener.fileno()
