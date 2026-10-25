"""
The folders the URDF picker browses, as the plan builder lists and serves them.
"""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from urllib.parse import urlencode

import pytest

from cramera.http.messages import HttpMethod, Request
from cramera_plan_builder.exceptions import FolderNotReadable, NotAFolder
from cramera_plan_builder.urdf_folders import UrdfFolders
from cramera_protocol.plan_builder import (
    PlanBuilderName,
    PlanBuilderRoute,
    UrdfFolder,
    UrdfFolderParameter,
)
from cramera_protocol.viewer import ViewerRoute

from .conftest import HEADERS


@pytest.fixture
def worlds(tmp_path):
    """
    :return: A folder of two URDFs, a xacro file, a mesh, a folder and hidden entries.
    """
    for name in ("kitchen.urdf", "apartment.urdf", "pr2.urdf.xacro", "cup.stl"):
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "meshes").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / ".hidden.urdf").write_text("", encoding="utf-8")
    return tmp_path


def test_a_folder_lists_its_folders_and_urdf_files(worlds):
    folder = UrdfFolders().listing(str(worlds))
    assert folder.path == str(worlds.resolve())
    assert folder.parent == str(worlds.resolve().parent)
    assert folder.folders == ["meshes"]
    assert folder.files == ["apartment.urdf", "kitchen.urdf", "pr2.urdf.xacro"]


def test_without_a_folder_the_home_folder_is_listed(worlds):
    assert UrdfFolders(home=worlds).listing(None).files == [
        "apartment.urdf",
        "kitchen.urdf",
        "pr2.urdf.xacro",
    ]


def test_the_root_has_no_parent():
    assert UrdfFolders().listing("/").parent is None


def test_a_file_or_missing_path_is_no_folder(worlds):
    for given in (str(worlds / "kitchen.urdf"), str(worlds / "none")):
        with pytest.raises(NotAFolder):
            UrdfFolders().listing(given)


@pytest.mark.skipif(os.geteuid() == 0, reason="root may list every folder")
def test_a_folder_that_may_not_be_listed_is_refused(worlds):
    locked = worlds / "meshes"
    locked.chmod(0)
    try:
        with pytest.raises(FolderNotReadable):
            UrdfFolders().listing(str(locked))
    finally:
        locked.chmod(0o755)


def folder_request(answerer, query: str):
    """
    :return: The answer to listing a folder with the query.
    """
    return answerer.answer(
        Request(
            method=HttpMethod.GET,
            path=f"{ViewerRoute.PLUGIN_API}{PlanBuilderName.PLUGIN}/{PlanBuilderRoute.URDF_FOLDER}",
            query=query,
            headers=HEADERS,
        )
    )


def test_the_route_lists_the_named_folder(answerer, worlds):
    answer = folder_request(answerer, urlencode({UrdfFolderParameter.PATH: worlds}))
    folder = UrdfFolder.from_json(json.loads(answer.body))
    assert answer.status == HTTPStatus.OK
    assert folder.files == ["apartment.urdf", "kitchen.urdf", "pr2.urdf.xacro"]


def test_the_route_refuses_a_path_that_is_no_folder(answerer, worlds):
    query = urlencode({UrdfFolderParameter.PATH: worlds / "kitchen.urdf"})
    assert folder_request(answerer, query).status == HTTPStatus.NOT_FOUND
