"""
Reading the file references inside the asset formats of a bundle.
"""

from __future__ import annotations

import pytest

from cramera_offline.exceptions import InvalidReference, UnreadableFile
from cramera_offline.references import (
    ColladaReferences,
    GlbReferences,
    GltfReferences,
    MaterialLibraryReferences,
    ObjReferences,
    ReferenceReaders,
    UrdfReferences,
    WavefrontStatement,
)

# %% models and documents


def test_a_urdf_references_its_meshes_and_textures(complete_bundle):
    assert UrdfReferences().references(complete_bundle / "robot.urdf") == [
        "meshes/part.dae",
        "textures/paint%20coat.svg",
    ]


def test_a_collada_document_references_its_images_but_not_its_effect_parameters(
    complete_bundle,
):
    assert ColladaReferences().references(complete_bundle / "meshes/part.dae") == [
        "../textures/paint%20coat.svg"
    ]


def test_a_damaged_xml_file_is_unreadable(broken_bundle):
    with pytest.raises(UnreadableFile):
        UrdfReferences().references(broken_bundle / "broken.urdf")


# %% wavefront


def test_an_obj_mesh_references_every_library_of_its_mtllib_line(complete_bundle):
    assert ObjReferences().references(complete_bundle / "meshes/object.obj") == [
        "materials/surface.mtl",
        "materials/second material.mtl",
    ]


def test_an_obj_mesh_without_materials_references_nothing(broken_bundle):
    assert ObjReferences().references(broken_bundle / "meshes/plain.obj") == []


def test_an_empty_mtllib_line_names_no_file(broken_bundle):
    with pytest.raises(InvalidReference):
        ObjReferences().references(broken_bundle / "meshes/empty_library.obj")


def test_a_material_library_references_its_maps_after_their_options(complete_bundle):
    texture = "../../textures/paint%20coat.svg"
    assert MaterialLibraryReferences().references(
        complete_bundle / "meshes/materials/surface.mtl"
    ) == [texture, texture, texture]


@pytest.mark.parametrize(
    "library",
    ["unknown_option", "missing_filename", "empty_vector", "empty_directive"],
)
def test_a_texture_statement_without_a_file_name_is_invalid(broken_bundle, library):
    with pytest.raises(InvalidReference):
        MaterialLibraryReferences().references(
            broken_bundle / f"meshes/materials/{library}.mtl"
        )


def test_a_comment_ends_a_statement():
    assert WavefrontStatement('mtllib "a b.mtl" c.mtl # d.mtl').tokens() == [
        "mtllib",
        "a b.mtl",
        "c.mtl",
    ]


# %% gltf


def test_a_gltf_mesh_references_its_buffers_and_images(complete_bundle):
    assert GltfReferences().references(complete_bundle / "meshes/object.gltf") == [
        "geometry.bin",
        "data:application/octet-stream;base64,AAAA",
        "../textures/paint%20coat.svg?version=1#image",
        "data:image/png;base64,AAAA",
    ]


def test_a_glb_mesh_references_what_its_json_chunk_references(complete_bundle):
    assert GlbReferences().references(
        complete_bundle / "meshes/object.glb"
    ) == GltfReferences().references(complete_bundle / "meshes/object.gltf")


@pytest.mark.parametrize(
    "mesh",
    [
        "meshes/invalid_header.glb",
        "meshes/invalid_chunk.glb",
        "meshes/no_json.glb",
        "meshes/not_json.gltf",
        "meshes/list.gltf",
    ],
)
def test_a_damaged_gltf_mesh_is_unreadable(broken_bundle, mesh):
    with pytest.raises(UnreadableFile):
        ReferenceReaders().references(broken_bundle / mesh)


def test_a_glb_file_shorter_than_its_header_has_no_json_chunk():
    assert GlbReferences().json_chunk_of(b"glTF") is None


# %% formats


def test_formats_are_chosen_by_suffix_without_regard_to_case(tmp_path, complete_bundle):
    shouting = tmp_path / "ROBOT.URDF"
    shouting.write_bytes((complete_bundle / "robot.urdf").read_bytes())
    assert ReferenceReaders().references(shouting) == UrdfReferences().references(
        complete_bundle / "robot.urdf"
    )


def test_formats_without_references_reference_nothing(complete_bundle):
    assert ReferenceReaders().references(complete_bundle / "meshes/geometry.bin") == []
