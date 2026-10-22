"""
Rigid transforms, bounds, triangulation of polygon meshes, tessellation of implicit
shapes, and the names the converter hands out.
"""

from __future__ import annotations

import numpy
import pytest
from scipy.spatial.transform import Rotation

from cramera_usd.geometry.bounds import PointBounds
from cramera_usd.geometry.meshes import (
    Interpolation,
    PolygonMesh,
    PrimvarData,
    TriangleMesh,
)
from cramera_usd.geometry.axes import Axis
from cramera_usd.geometry.shapes import ShapeTessellation
from cramera_usd.geometry.transforms import RigidTransform, TransformTrack
from cramera_usd.names import (
    FIRST_REPEAT_NUMBER,
    GeneratedName,
    NameSeparator,
    PrimNames,
    UniqueNames,
)

# %% helpers


def unit_square(**primvars) -> PolygonMesh:
    """
    :param primvars: Extra fields of the polygon mesh.
    :return: A counter-clockwise unit square in the XY plane as one quad.
    """
    return PolygonMesh(
        points=numpy.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float),
        face_vertex_counts=numpy.array([4]),
        face_vertex_indices=numpy.array([0, 1, 2, 3]),
        **primvars,
    )


def facing(mesh: TriangleMesh) -> numpy.ndarray:
    """
    :param mesh: Triangles.
    :return: The unit geometric normal of every triangle.
    """
    corners = mesh.points[mesh.triangles]
    normals = numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    return normals / numpy.linalg.norm(normals, axis=1, keepdims=True)


def signed_volume(mesh: TriangleMesh) -> float:
    """
    :param mesh: A closed triangle mesh.
    :return: The enclosed volume, positive when the triangles face outwards.
    """
    corners = mesh.points[mesh.triangles]
    return float(
        numpy.einsum(
            "ij,ij->i", corners[:, 0], numpy.cross(corners[:, 1], corners[:, 2])
        ).sum()
        / 6.0
    )


def turned(angle: float) -> RigidTransform:
    """
    :param angle: An angle in radians.
    :return: A turn about Z.
    """
    return RigidTransform.from_rotation(
        Rotation.from_rotvec([0.0, 0.0, angle]).as_matrix()
    )


# %% polygon meshes


class TestPolygonTriangulation:
    """
    Fan triangulation keeping the winding and spreading primvars.
    """

    def test_quad_becomes_two_triangles_facing_up(self):
        mesh = unit_square().triangulate()
        assert mesh.triangles.tolist() == [[0, 1, 2], [0, 2, 3]]
        assert numpy.allclose(facing(mesh), [[0, 0, 1], [0, 0, 1]])

    def test_left_handed_faces_are_reversed(self):
        mesh = unit_square(left_handed=True).triangulate()
        assert numpy.allclose(facing(mesh), [[0, 0, -1], [0, 0, -1]])

    def test_vertex_primvars_keep_points_shared(self):
        coordinates = numpy.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        mesh = unit_square(
            texture_coordinates=PrimvarData(coordinates, Interpolation.VERTEX)
        ).triangulate()
        assert len(mesh.points) == len(coordinates)
        assert numpy.array_equal(mesh.texture_coordinates, coordinates)

    def test_face_varying_primvars_split_points_per_corner(self):
        coordinates = numpy.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        mesh = unit_square(
            texture_coordinates=PrimvarData(coordinates, Interpolation.FACE_VARYING)
        ).triangulate()
        corners = mesh.triangles.ravel()
        assert numpy.array_equal(
            mesh.texture_coordinates[corners], coordinates[[0, 1, 2, 0, 2, 3]]
        )
        assert numpy.array_equal(
            mesh.points[corners][:, :2], coordinates[[0, 1, 2, 0, 2, 3]]
        )

    def test_uniform_normals_give_every_face_its_own_vertices(self):
        normal = numpy.array([[0.0, 0.0, 1.0]])
        mesh = unit_square(
            normals=PrimvarData(normal, Interpolation.UNIFORM)
        ).triangulate()
        assert numpy.allclose(mesh.normals, normal)

    def test_constant_normal_is_repeated_on_every_corner(self):
        normal = numpy.array([[0.0, 0.0, 1.0]])
        mesh = unit_square(
            normals=PrimvarData(normal, Interpolation.CONSTANT)
        ).triangulate()
        assert numpy.allclose(mesh.normals[mesh.triangles.ravel()], normal)

    @pytest.mark.parametrize(
        "interpolation",
        [Interpolation.FACE_VARYING, Interpolation.CONSTANT, Interpolation.VERTEX],
    )
    def test_mismatched_primvar_is_dropped(self, interpolation):
        mesh = unit_square(
            normals=PrimvarData(numpy.zeros((0, 3)), interpolation)
        ).triangulate()
        assert mesh.normals is None

    def test_faces_with_fewer_than_three_corners_are_dropped(self):
        mesh = PolygonMesh(
            points=numpy.eye(3),
            face_vertex_counts=numpy.array([2, 3]),
            face_vertex_indices=numpy.array([0, 1, 0, 1, 2]),
        ).triangulate()
        assert mesh.triangles.tolist() == [[0, 1, 2]]
        assert mesh.faces.tolist() == [1]

    def test_subset_keeps_only_the_vertices_its_triangles_use(self):
        mesh = unit_square().triangulate()
        subset = mesh.subset(numpy.array([True, False]))
        assert subset.triangles.tolist() == [[0, 1, 2]]
        assert numpy.array_equal(subset.points, mesh.points[:3])


def test_mirroring_transform_keeps_triangles_facing_outwards():
    mirror = numpy.diag([1.0, 1.0, -1.0, 1.0])
    box = ShapeTessellation().box(1.0).transformed(mirror)
    assert signed_volume(box) == pytest.approx(1.0)


def test_missing_normals_are_computed_from_the_faces():
    mesh = unit_square().triangulate()
    assert numpy.allclose(mesh.vertex_normals(), [0.0, 0.0, 1.0])


# %% implicit shapes


@pytest.mark.parametrize("axis", list(Axis))
def test_round_shapes_are_closed_and_face_outwards(axis):
    tessellation = ShapeTessellation(segments=64, rings=32)
    radius, height = 0.5, 2.0
    assert signed_volume(tessellation.cylinder(radius, height, axis)) == pytest.approx(
        numpy.pi * radius**2 * height, rel=0.01
    )
    assert signed_volume(tessellation.cone(radius, height, axis)) == pytest.approx(
        numpy.pi * radius**2 * height / 3.0, rel=0.01
    )
    assert signed_volume(tessellation.capsule(radius, height, axis)) == pytest.approx(
        numpy.pi * radius**2 * (height + 4.0 * radius / 3.0), rel=0.01
    )


@pytest.mark.parametrize("axis", list(Axis))
def test_round_shapes_extend_along_their_axis(axis):
    height = 2.0
    cylinder = ShapeTessellation().cylinder(0.5, height, axis)
    extent = cylinder.points.max(axis=0) - cylinder.points.min(axis=0)
    assert extent[axis.index] == pytest.approx(height)


@pytest.mark.parametrize("axis", list(Axis))
def test_cone_apex_lies_on_the_positive_side_of_its_axis(axis):
    radius, height = 0.5, 2.0
    cone = ShapeTessellation().cone(radius, height, axis)
    direction = axis.direction
    along = cone.points @ direction
    tip = cone.points[numpy.isclose(along, along.max())]
    assert along.max() == pytest.approx(height / 2.0)
    assert numpy.allclose(tip - numpy.outer(tip @ direction, direction), 0.0)


def test_sphere_normals_point_away_from_the_centre():
    radius = 2.0
    sphere = ShapeTessellation().sphere(radius)
    assert numpy.allclose(sphere.normals * radius, sphere.points)
    assert signed_volume(sphere) > 0.0


def test_box_has_one_flat_normal_per_face():
    size = 2.0
    box = ShapeTessellation().box(size)
    assert numpy.allclose(abs(box.points).max(axis=0), size / 2.0)
    assert numpy.allclose(facing(box), box.normals[box.triangles[:, 0]])


# %% transforms


def test_rigid_part_removes_scale_and_mirroring():
    translation = [1.0, 2.0, 3.0]
    matrix = turned(0.3).matrix @ numpy.diag([2.0, 2.0, -2.0, 1.0])
    matrix[:3, 3] = translation
    rigid = RigidTransform.rigid_part(matrix)
    assert numpy.linalg.det(rigid.rotation) == pytest.approx(1.0)
    assert rigid.rotation @ rigid.rotation.T == pytest.approx(numpy.eye(3))
    assert rigid.translation == pytest.approx(translation)


def test_inverse_undoes_a_transform():
    transform = turned(0.7) @ RigidTransform.from_translation(
        numpy.array([1.0, -2.0, 0.5])
    )
    assert (transform @ transform.inverse()).is_close(RigidTransform())


def test_translation_and_quaternion_build_the_written_pose():
    translation = numpy.array([1.0, -2.0, 0.5])
    quaternion = Rotation.from_rotvec([0.0, 0.0, 0.4]).as_quat()
    pose = RigidTransform.from_translation_quaternion(translation, quaternion)
    written = pose.to_protocol()
    assert [written.x, written.y, written.z] == pytest.approx(translation)
    assert [written.qx, written.qy, written.qz, written.qw] == pytest.approx(quaternion)


def test_a_track_composes_with_a_single_transform_frame_by_frame():
    track = TransformTrack.constant(turned(0.2), 3)
    shifted = track @ RigidTransform.from_translation(numpy.array([1.0, 0.0, 0.0]))
    assert shifted.frame_count == track.frame_count
    assert shifted.at_frame(2).is_close(
        turned(0.2) @ RigidTransform.from_translation(numpy.array([1.0, 0.0, 0.0]))
    )


# %% bounds


def test_central_bounds_leave_out_sparse_outliers():
    points = numpy.concatenate([numpy.zeros((99, 3)), [[100.0, 100.0, 100.0]]])
    central = PointBounds.central(points, 0.9)
    assert central.maximum == pytest.approx([0.0, 0.0, 0.0])
    assert PointBounds.of_points(points).diagonal == pytest.approx(
        numpy.linalg.norm([100.0, 100.0, 100.0])
    )


def test_bounds_are_written_rounded():
    bounds = PointBounds(numpy.array([0.12345, 0.0, 0.0]), numpy.ones(3))
    assert bounds.to_protocol(2).minimum.x == round(0.12345, 2)


# %% names


def test_repeated_names_are_numbered_from_two():
    names = UniqueNames()
    claimed = [names.claim(name) for name in ["Link", "Link", "Hand", "Link"]]
    assert claimed == [
        "Link",
        f"Link{NameSeparator.NUMBER}{FIRST_REPEAT_NUMBER}",
        "Hand",
        f"Link{NameSeparator.NUMBER}{FIRST_REPEAT_NUMBER + 1}",
    ]


def test_prim_names_drop_the_default_prim_and_flatten_the_path():
    names = PrimNames("/World")
    assert names.name_of("/World/Cabinet/Door") == NameSeparator.FLATTENED_PATH.join(
        ["Cabinet", "Door"]
    )
    assert names.name_of("/World/Cabinet/Door") == names.name_of("/World/Cabinet/Door")


def test_the_pseudo_root_is_named_the_world():
    assert PrimNames("").name_of("/") == GeneratedName.WORLD
