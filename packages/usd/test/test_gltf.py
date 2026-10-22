"""
The GLB written for one link: merged geometry, flipped texture coordinates, materials
with extensions and embedded textures.
"""

from __future__ import annotations

import io
import json

import numpy
import trimesh

from cramera_usd.gltf.document import GltfDocument
from cramera_usd.gltf.format import (
    AttributeName,
    GltfExtension,
    GltfKey,
    MaterialKey,
    NodeExtra,
)
from cramera_usd.gltf.link import LinkGltf
from cramera_usd.gltf.material import GltfMaterial
from cramera_usd.materials.channels import RoughnessMetallicTexture, ScalarChannel
from cramera_usd.materials.physically_based import (
    AlphaMode,
    PhysicallyBasedMaterial,
    TextureTransform,
)
from cramera_usd.materials.transmission import TransmissionBlending
from cramera_usd.geometry.meshes import TriangleMesh
from cramera_usd.geometry.transforms import RigidTransform
from cramera_usd.scene.kinematics import Link, LinkMesh
from cramera_usd.scene.materials import ColorSpace, TextureFile

from .dataset.glb import GlbContent
from .dataset.stages import DATASET, TEXTURES


def quad(path: str, material: str, offset: float = 0.0) -> LinkMesh:
    """
    :param path: The prim path.
    :param material: The material name.
    :param offset: Shift along X.
    :return: A textured unit quad.
    """
    return LinkMesh(
        path=path,
        geometry=TriangleMesh(
            points=numpy.array(
                [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=numpy.float32
            )
            + [offset, 0, 0],
            triangles=numpy.array([[0, 1, 2], [0, 2, 3]], dtype=numpy.uint32),
            normals=numpy.tile(numpy.array([0, 0, 1], numpy.float32), (4, 1)),
            texture_coordinates=numpy.array(
                [[0, 0], [1, 0], [1, 1], [0, 1]], dtype=numpy.float32
            ),
        ),
        material=material,
    )


def link_with(*meshes: LinkMesh) -> Link:
    """
    :param meshes: Meshes.
    :return: A link holding the meshes.
    """
    return Link("Station", "/World/Station", RigidTransform(), meshes=list(meshes))


ALBEDO = TextureFile(TEXTURES / "albedo.png", ColorSpace.SRGB)
"""
The colour texture of the tests' textured material.
"""

VIEWER_GLASS = DATASET / "blended_glass.gltf"
"""
The converted glass material the viewer's tests load.
"""


# %% geometry


def test_texture_v_axis_is_flipped():
    mesh = quad("/World/Station/Decal", "paint")
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(mesh),
            {"paint": PhysicallyBasedMaterial("paint", base_color_texture=ALBEDO)},
        ).encode()
    )
    coordinates = content.accessor(
        content.primitive(0)[GltfKey.ATTRIBUTES][AttributeName.TEXTURE_COORDINATES]
    )
    assert numpy.array_equal(coordinates[:, 0], mesh.geometry.texture_coordinates[:, 0])
    assert numpy.array_equal(
        coordinates[:, 1], 1.0 - mesh.geometry.texture_coordinates[:, 1]
    )


def test_meshes_sharing_a_material_become_one_node_named_by_their_common_prim():
    first, second = quad("/World/Station/A/Mesh", "paint"), quad(
        "/World/Station/B/Mesh", "paint", 2.0
    )
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(first, second),
            {"paint": PhysicallyBasedMaterial("paint")},
            {"/World/Station": {"sdt": {"class": "Station"}}},
        ).encode()
    )
    assert [node[GltfKey.NAME] for node in content.document[GltfKey.NODES]] == [
        "/World/Station"
    ]
    assert content.document[GltfKey.NODES][0][GltfKey.EXTRAS] == {
        NodeExtra.USD_PATH: "/World/Station",
        NodeExtra.USD_PATHS: [first.path, second.path],
        "sdt": {"class": "Station"},
    }
    primitive = content.primitive(0)
    positions = content.accessor(primitive[GltfKey.ATTRIBUTES][AttributeName.POSITION])
    assert numpy.array_equal(
        positions, numpy.concatenate([first.geometry.points, second.geometry.points])
    )
    assert content.accessor(primitive[GltfKey.INDICES]).tolist() == [
        0,
        1,
        2,
        0,
        2,
        3,
        4,
        5,
        6,
        4,
        6,
        7,
    ]


def test_untextured_material_drops_texture_coordinates():
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(quad("/World/Station/Box", "grey")),
            {"grey": PhysicallyBasedMaterial("grey")},
        ).encode()
    )
    assert (
        AttributeName.TEXTURE_COORDINATES
        not in content.primitive(0)[GltfKey.ATTRIBUTES]
    )


def test_double_sided_mesh_gets_its_own_material():
    single, double = quad("/World/Station/A", "paint"), quad(
        "/World/Station/B", "paint"
    )
    double.double_sided = True
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(single, double), {"paint": PhysicallyBasedMaterial("paint")}
        ).encode()
    )
    assert [
        material[MaterialKey.DOUBLE_SIDED]
        for material in content.document[GltfKey.MATERIALS]
    ] == [False, True]


# %% materials


def test_glass_is_drawn_blended_and_keeps_its_physical_values_in_extras():
    glass = PhysicallyBasedMaterial(
        "glass",
        base_color_factor=(0.9, 0.95, 1.0, 1.0),
        roughness_factor=0.1,
        transmission=1.0,
        index_of_refraction=1.52,
        alpha_mode=AlphaMode.BLEND,
        double_sided=True,
    )
    drawn = TransmissionBlending().approximate(glass)
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(quad("/World/Station/Pane", "glass")), {"glass": glass}
        ).encode()
    )
    material = content.document[GltfKey.MATERIALS][0]
    assert material[MaterialKey.METALLIC_ROUGHNESS] == {
        MaterialKey.BASE_COLOR_FACTOR: list(drawn.base_color_factor),
        MaterialKey.METALLIC_FACTOR: drawn.metallic_factor,
        MaterialKey.ROUGHNESS_FACTOR: drawn.roughness_factor,
    }
    assert material[MaterialKey.ALPHA_MODE] == AlphaMode.BLEND
    assert material[MaterialKey.DOUBLE_SIDED] is True
    assert material[GltfKey.EXTRAS] == {
        MaterialKey.TRANSMISSION_FACTOR: glass.transmission,
        MaterialKey.INDEX_OF_REFRACTION: glass.index_of_refraction,
        MaterialKey.BASE_COLOR_FACTOR: list(glass.base_color_factor),
        MaterialKey.METALLIC_FACTOR: glass.metallic_factor,
    }
    assert GltfKey.EXTENSIONS not in material
    assert GltfKey.EXTENSIONS_USED not in content.document


def test_glass_with_only_a_metalness_texture_is_written_with_factors():
    roughness = ScalarChannel(0.2)
    glass = PhysicallyBasedMaterial(
        "glass",
        roughness_factor=1.0,
        metallic_factor=1.0,
        metallic_roughness_texture=RoughnessMetallicTexture(
            roughness, ScalarChannel(0.0, TextureFile(TEXTURES / "metallic.png"))
        ),
        transmission=1.0,
        alpha_mode=AlphaMode.BLEND,
        double_sided=True,
    )
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(quad("/World/Station/Pane", "glass")), {"glass": glass}
        ).encode()
    )
    written = content.document[GltfKey.MATERIALS][0][MaterialKey.METALLIC_ROUGHNESS]
    assert MaterialKey.METALLIC_ROUGHNESS_TEXTURE not in written
    assert written[MaterialKey.ROUGHNESS_FACTOR] == roughness.constant
    assert written[MaterialKey.METALLIC_FACTOR] == 1.0


def test_viewer_glass_fixture_holds_the_extras_the_writer_writes():
    glass = PhysicallyBasedMaterial("glass", transmission=1.0)
    written = GltfMaterial(glass, GltfDocument()).to_json()
    fixture = json.loads(VIEWER_GLASS.read_text())[GltfKey.MATERIALS][0]
    assert fixture[MaterialKey.ALPHA_MODE] == written[MaterialKey.ALPHA_MODE]
    assert fixture[GltfKey.EXTRAS].keys() == written[GltfKey.EXTRAS].keys()


def test_opaque_material_writes_its_index_of_refraction_as_an_extension():
    plastic = PhysicallyBasedMaterial("plastic", index_of_refraction=1.59)
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(quad("/World/Station/Cover", "plastic")), {"plastic": plastic}
        ).encode()
    )
    material = content.document[GltfKey.MATERIALS][0]
    assert material[GltfKey.EXTENSIONS] == {
        GltfExtension.INDEX_OF_REFRACTION: {
            MaterialKey.INDEX_OF_REFRACTION: plastic.index_of_refraction
        }
    }
    assert GltfKey.EXTRAS not in material


def test_textures_are_embedded_once_with_their_transform():
    transform = TextureTransform(offset=(0.0, -1.0), scale=(2.0, 2.0))
    material = PhysicallyBasedMaterial(
        "tiles",
        base_color_texture=ALBEDO,
        emissive_texture=ALBEDO,
        emissive_factor=(1.0, 1.0, 1.0),
        metallic_roughness_texture=RoughnessMetallicTexture(
            ScalarChannel(0.5, TextureFile(TEXTURES / "roughness.png")),
            ScalarChannel(0.0),
        ),
        texture_transform=transform,
    )
    content = GlbContent.of_bytes(
        LinkGltf(
            link_with(quad("/World/Station/Floor", "tiles")), {"tiles": material}
        ).encode()
    )
    written = content.document[GltfKey.MATERIALS][0]
    base_color = written[MaterialKey.METALLIC_ROUGHNESS][MaterialKey.BASE_COLOR_TEXTURE]
    assert len(content.document[GltfKey.IMAGES]) == 2
    assert (
        written[MaterialKey.EMISSIVE_TEXTURE][GltfKey.INDEX]
        == base_color[GltfKey.INDEX]
    )
    assert base_color[GltfKey.EXTENSIONS] == {
        GltfExtension.TEXTURE_TRANSFORM: {
            GltfKey.OFFSET: list(transform.offset),
            GltfKey.SCALE: list(transform.scale),
        }
    }
    assert content.embedded(0) == ALBEDO.path.read_bytes()


def test_trimesh_loads_the_file():
    data = LinkGltf(
        link_with(quad("/World/Station/Decal", "paint")),
        {"paint": PhysicallyBasedMaterial("paint", base_color_texture=ALBEDO)},
    ).encode()
    scene = trimesh.load(io.BytesIO(data), file_type="glb")
    assert sum(len(geometry.faces) for geometry in scene.geometry.values()) == 2
