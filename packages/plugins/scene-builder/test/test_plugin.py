"""
The scene builder as the viewer serves it: its information, routes, browser files and
the statuses of refused requests.
"""

from __future__ import annotations

import json
from dataclasses import replace
from http import HTTPStatus
from importlib.metadata import entry_points
from urllib.parse import urlencode

import pytest

from cramera.http.messages import HttpMethod, MediaType, Request
from cramera.plugins import PluginLoader
from cramera.scenes import SceneSource
from cramera_protocol.scene_builder import (
    DraftList,
    DraftRecord,
    PointCloudFormat,
    ResourceDescription,
    ResourceKind,
    SceneBuilderCatalog,
    SceneBuilderName,
    SceneBuilderRoute,
    SceneDraft,
    TemplateParameter,
)
from cramera_protocol.viewer import ErrorKey, PluginGroup, ViewerRoute
from cramera_scene_builder.plugin import (
    SceneBuilderPlugin,
    SceneBuilderStorage,
)
from cramera_scene_builder.point_clouds import SAMPLE_HEADER

from .conftest import DATASET, HEADERS, LIBRARY_ROOT, send

CLOUD = DATASET / "point_clouds" / "colored_binary.pcd"
"""
A valid point cloud to upload.
"""


def decoded(response):
    return json.loads(response.body)


# %% plugin


def test_the_plugin_is_installed_under_its_name():
    (entry_point,) = [
        entry
        for entry in entry_points(group=PluginGroup.VIEWER)
        if entry.name == SceneBuilderName.PLUGIN
    ]
    (plugin,) = [
        plugin
        for plugin in PluginLoader([entry_point]).load()
        if plugin.name() == SceneBuilderName.PLUGIN
    ]
    assert isinstance(plugin, SceneBuilderPlugin)


def test_the_plugin_reports_its_version(plugin):
    assert plugin.info().version == plugin.version()


def test_storage_lies_below_the_data_directory(locations):
    storage = SceneBuilderStorage.of(locations)
    assert storage.drafts.is_relative_to(locations.data)
    assert storage.point_clouds.is_relative_to(locations.data)
    assert storage.drafts != storage.point_clouds


# %% catalog and templates


def test_the_catalog_offers_resources_scenes_drafts_and_limits(
    get, library, catalog, limits
):
    offered = SceneBuilderCatalog.from_json(decoded(get(SceneBuilderRoute.CATALOG)))
    assert offered.resources == library.resources()
    assert offered.scenes == catalog.index().scenes
    assert offered.drafts == []
    assert offered.limits == limits


def test_a_template_starts_a_draft_from_a_scene(get, catalog):
    answer = get(
        SceneBuilderRoute.TEMPLATE, urlencode({TemplateParameter.SCENE: "cell"})
    )
    draft = SceneDraft.from_json(decoded(answer))
    assert draft.source_scene == "cell"
    assert draft.instances[0].asset.startswith(f"{SceneSource.DEMO}/cell/")


@pytest.mark.parametrize(
    "query",
    [
        "",
        urlencode(
            [(TemplateParameter.SCENE, "cell"), (TemplateParameter.SCENE, "cell")]
        ),
        urlencode({TemplateParameter.SCENE: "cell", "extra": "1"}),
    ],
)
def test_a_template_request_must_name_one_scene(get, query):
    assert get(SceneBuilderRoute.TEMPLATE, query).status is HTTPStatus.BAD_REQUEST


def test_a_template_of_an_unknown_scene_is_not_found(get):
    answer = get(SceneBuilderRoute.TEMPLATE, urlencode({TemplateParameter.SCENE: "x"}))
    assert answer.status is HTTPStatus.NOT_FOUND


# %% drafts


def test_a_posted_draft_is_saved_listed_and_loaded(get, post, read_json):
    body = json.dumps(read_json("drafts/new_draft.json")).encode("utf-8")
    saved = DraftRecord.from_json(decoded(post(SceneBuilderRoute.DRAFTS, body)))
    listed = DraftList.from_json(decoded(get(SceneBuilderRoute.DRAFTS)))
    loaded = DraftRecord.from_json(
        decoded(get(f"{SceneBuilderRoute.DRAFT}{saved.identifier}"))
    )
    assert [summary.identifier for summary in listed.drafts] == [saved.identifier]
    assert loaded == saved


@pytest.mark.parametrize(
    "name, status",
    [
        ("truncated_body", HTTPStatus.BAD_REQUEST),
        ("zero_scale", HTTPStatus.BAD_REQUEST),
        ("unknown_asset", HTTPStatus.NOT_FOUND),
        ("dependency_asset", HTTPStatus.UNPROCESSABLE_ENTITY),
        ("climbing_asset", HTTPStatus.BAD_REQUEST),
    ],
)
def test_refused_drafts_are_answered_with_their_status(post, name, status):
    body = (DATASET / "drafts" / "invalid" / f"{name}.json").read_bytes()
    answer = post(SceneBuilderRoute.DRAFTS, body)
    assert answer.status is status
    assert ErrorKey.ERROR in decoded(answer)


def test_a_draft_body_larger_than_a_draft_is_refused(post, limits, read_json):
    body = json.dumps(read_json("drafts/new_draft.json")).encode("utf-8")
    padded = body + b" " * limits.maximum_document_bytes
    answer = post(SceneBuilderRoute.DRAFTS, padded)
    assert answer.status is HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_a_draft_that_is_no_draft_document_is_refused(post):
    answer = post(SceneBuilderRoute.DRAFTS, json.dumps({"document": []}).encode())
    assert answer.status is HTTPStatus.BAD_REQUEST


def test_an_unknown_draft_is_not_found(get):
    assert get(f"{SceneBuilderRoute.DRAFT}missing").status is HTTPStatus.NOT_FOUND


# %% assets


def test_a_library_model_is_served_with_relative_references(get):
    answer = get(f"{SceneBuilderRoute.ASSETS}{LIBRARY_ROOT}/kitchen/cabinet.urdf")
    assert answer.status is HTTPStatus.OK
    assert answer.media_type is MediaType.XML


@pytest.mark.parametrize(
    "path, status",
    [
        (f"{LIBRARY_ROOT}/../{LIBRARY_ROOT}/notes.txt", HTTPStatus.BAD_REQUEST),
        (f"{LIBRARY_ROOT}/notes.txt", HTTPStatus.FORBIDDEN),
        (f"{LIBRARY_ROOT}/kitchen/gone.urdf", HTTPStatus.NOT_FOUND),
        ("elsewhere/kitchen/cabinet.urdf", HTTPStatus.NOT_FOUND),
        (f"{LIBRARY_ROOT}/unsafe/missing.urdf", HTTPStatus.UNPROCESSABLE_ENTITY),
    ],
)
def test_refused_asset_requests_are_answered_with_their_status(get, path, status):
    assert get(f"{SceneBuilderRoute.ASSETS}{path}").status is status


# %% point clouds


def test_an_uploaded_cloud_joins_the_library(get, post):
    answer = post(
        f"{SceneBuilderRoute.POINT_CLOUDS}{PointCloudFormat.PCD}", CLOUD.read_bytes()
    )
    uploaded = ResourceDescription.from_json(decoded(answer))
    offered = SceneBuilderCatalog.from_json(decoded(get(SceneBuilderRoute.CATALOG)))
    assert uploaded.kind is ResourceKind.POINT_CLOUD
    assert uploaded.point_cloud.file_format is PointCloudFormat.PCD
    assert uploaded in offered.resources


def test_an_upload_of_an_unknown_format_is_not_found(post):
    answer = post(f"{SceneBuilderRoute.POINT_CLOUDS}xyz", CLOUD.read_bytes())
    assert answer.status is HTTPStatus.NOT_FOUND


def test_a_malformed_upload_is_unprocessable(post):
    answer = post(
        f"{SceneBuilderRoute.POINT_CLOUDS}{PointCloudFormat.PLY}", CLOUD.read_bytes()
    )
    assert answer.status is HTTPStatus.UNPROCESSABLE_ENTITY


def test_the_sample_of_an_uploaded_cloud_is_served(post, get):
    answer = post(
        f"{SceneBuilderRoute.POINT_CLOUDS}{PointCloudFormat.PCD}", CLOUD.read_bytes()
    )
    uploaded = ResourceDescription.from_json(decoded(answer))
    sample = get(f"{SceneBuilderRoute.POINT_CLOUD_SAMPLES}{uploaded.identifier}")
    count, colored = SAMPLE_HEADER.unpack_from(sample.body)
    assert sample.media_type is MediaType.BINARY
    assert (count, colored) == (uploaded.point_cloud.finite_point_count, 1)


def test_the_sample_of_a_model_is_refused(get):
    answer = get(
        f"{SceneBuilderRoute.POINT_CLOUD_SAMPLES}{LIBRARY_ROOT}/kitchen/cabinet.urdf"
    )
    assert answer.status is HTTPStatus.UNPROCESSABLE_ENTITY


def test_the_sample_of_a_file_larger_than_an_upload_is_refused(
    serve, environment, limits, workspace
):
    (workspace / LIBRARY_ROOT / "scan.pcd").write_bytes(CLOUD.read_bytes())
    bounded = replace(limits, maximum_point_cloud_bytes=len(CLOUD.read_bytes()) - 1)
    plugin = SceneBuilderPlugin(environment=environment, limits=bounded)
    answer = send(
        serve(plugin),
        HttpMethod.GET,
        f"{SceneBuilderRoute.POINT_CLOUD_SAMPLES}{LIBRARY_ROOT}/scan.pcd",
    )
    assert answer.status is HTTPStatus.REQUEST_ENTITY_TOO_LARGE
