"""
Library files as the browser's loaders receive them: model references rewritten into
paths relative to the model, and models with unsafe references refused.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree

import pytest

from cramera.http.messages import MediaType
from cramera_scene_builder.assets import AssetFiles, GltfName, UrdfName
from cramera_scene_builder.exceptions import (
    DocumentTypeDeclaration,
    ExternalDependency,
    MalformedResourceDocument,
    MissingDependency,
)
from cramera_scene_builder.resources import ResourceIdentifier

from .conftest import DATASET, LIBRARY_ROOT

# %% models


def mesh_references(body: bytes):
    document = ElementTree.fromstring(body)
    return [element.get(UrdfName.FILE_NAME) for element in document.iter(UrdfName.MESH)]


def test_urdf_references_become_paths_relative_to_the_model(library):
    answer = AssetFiles(library).answer(
        ResourceIdentifier(LIBRARY_ROOT, "kitchen/cabinet.urdf")
    )
    assert answer.media_type is MediaType.XML
    assert mesh_references(answer.body) == ["meshes/door.stl", "meshes/handle.obj"]


def test_gltf_references_become_paths_relative_to_the_file(library, read_json):
    answer = AssetFiles(library).answer(
        ResourceIdentifier(LIBRARY_ROOT, "props/cup.gltf")
    )
    original = read_json(f"{LIBRARY_ROOT}/props/cup.gltf")
    written = json.loads(answer.body)
    assert answer.media_type is MediaType.GLTF
    assert [buffer.get(GltfName.URI) for buffer in written[GltfName.BUFFERS]] == [
        buffer[GltfName.URI] for buffer in original[GltfName.BUFFERS]
    ]
    assert [image.get(GltfName.URI) for image in written[GltfName.IMAGES]] == [
        image.get(GltfName.URI) for image in original[GltfName.IMAGES]
    ]


def test_other_files_are_served_unchanged(library):
    answer = AssetFiles(library).answer(
        ResourceIdentifier(LIBRARY_ROOT, "kitchen/meshes/door.stl")
    )
    assert (
        answer.body == (DATASET / LIBRARY_ROOT / "kitchen/meshes/door.stl").read_bytes()
    )
    assert answer.media_type is MediaType.STL


# %% refusals


@pytest.mark.parametrize(
    "model, error",
    [
        ("unsafe/doctype.urdf", DocumentTypeDeclaration),
        ("unsafe/absolute.urdf", ExternalDependency),
        ("unsafe/web.urdf", ExternalDependency),
        ("unsafe/climbing_package.urdf", ExternalDependency),
        ("unsafe/missing.urdf", MissingDependency),
        ("unsafe/missing_package.urdf", MissingDependency),
        ("unsafe/malformed.urdf", MalformedResourceDocument),
        ("props/listing.gltf", MalformedResourceDocument),
        ("props/truncated.gltf", MalformedResourceDocument),
    ],
)
def test_models_with_unsafe_or_broken_references_are_refused(library, model, error):
    with pytest.raises(error) as refused:
        AssetFiles(library).answer(ResourceIdentifier(LIBRARY_ROOT, model))
    assert refused.value.identifier == f"{LIBRARY_ROOT}/{model}"
