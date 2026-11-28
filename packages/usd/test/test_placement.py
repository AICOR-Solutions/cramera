"""
Placing a converted stage in its bundle: a stage point becomes the bundle's origin, and
only the geometry over a rectangle of the floor plan is drawn.
"""

from __future__ import annotations

import numpy
import pytest

from cramera_protocol.bundle.conversion_report import ReportCount, SkipReason
from cramera_usd.commands.import_scene import (
    ImportCommand,
    ImportOption,
    ImportParser,
)
from cramera_usd.geometry.meshes import TriangleMesh
from cramera_usd.stage.placement import FloorRegion, StageOrigin
from cramera_usd.stage.reader import StageReader

from .dataset.stages import Stage, link_holding, world_points

# %% origin


def test_an_origin_places_the_stage_point_at_the_origin_facing_its_heading():
    origin = StageOrigin(x=1.0, y=2.0, z=0.5, yaw=90.0)
    plain = StageReader(Stage.GLASS_PANE.path).read()
    placed = StageReader(Stage.GLASS_PANE.path, origin=origin).read()
    before = world_points(link_holding(plain, "/World/Pane"), "/World/Pane")
    after = world_points(link_holding(placed, "/World/Pane"), "/World/Pane")
    relative = before - [1.0, 2.0, 0.5]
    # facing the stage's y axis, the stage's y is ahead (x) and its x is to the right
    assert numpy.allclose(
        after, numpy.stack([relative[:, 1], -relative[:, 0], relative[:, 2]], axis=1)
    )


def test_an_origin_moves_the_collision_boxes_with_the_geometry():
    origin = StageOrigin(x=0.3, y=-0.2, z=0.1, yaw=0.0)
    plain = StageReader(Stage.SHELF_WITH_TOTES.path).read()
    placed = StageReader(Stage.SHELF_WITH_TOTES.path, origin=origin).read()
    boxes = {
        box.path: link.pose.matrix @ box.pose.matrix
        for link in plain.links
        for box in link.collisions
    }
    for link in placed.links:
        for box in link.collisions:
            moved = link.pose.matrix @ box.pose.matrix
            assert numpy.allclose(
                moved[:3, 3], boxes[box.path][:3, 3] - [0.3, -0.2, 0.1]
            )


def test_the_stage_origin_leaves_the_stage_in_place():
    origin = StageOrigin(x=0.0, y=0.0, z=0.0, yaw=0.0)
    assert numpy.allclose(origin.bundle_from_stage(), numpy.eye(4))


# %% region


def every_point(converted) -> numpy.ndarray:
    return numpy.concatenate(
        [
            world_points(link, mesh.path)
            for link in converted.links
            for mesh in link.meshes
        ]
    )


def test_a_region_draws_only_the_geometry_over_it():
    whole = every_point(StageReader(Stage.GLASS_PANE.path).read())
    middle_x = float(numpy.median(whole[:, 0]))
    region = FloorRegion(-100.0, -100.0, middle_x, 100.0)
    cropped = every_point(StageReader(Stage.GLASS_PANE.path, region=region).read())
    assert (cropped[:, 0] <= middle_x + 1e-6).all()
    assert cropped[:, 0].max() == pytest.approx(middle_x, abs=1e-6)


def test_a_triangle_crossing_an_edge_is_cut_there_with_its_texture_stretched_along():
    mesh = TriangleMesh(
        points=numpy.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0], [0.0, 4.0, 0.0]]),
        triangles=numpy.array([[0, 1, 2]], dtype=numpy.uint32),
        normals=numpy.array([[0.0, 0.0, 1.0]] * 3),
        texture_coordinates=numpy.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]),
    )
    cropped = FloorRegion(-1.0, -1.0, 1.0, 1.0).crop(mesh, numpy.eye(4))
    corners = cropped.points[cropped.triangles].reshape(-1, 3)
    assert corners[:, :2].min() == pytest.approx(0.0)
    assert corners[:, :2].max() == pytest.approx(1.0)
    # a unit square of the floor plan, each corner textured where it lies
    area = (
        0.5
        * numpy.linalg.norm(
            numpy.cross(
                cropped.points[cropped.triangles[:, 1]]
                - cropped.points[cropped.triangles[:, 0]],
                cropped.points[cropped.triangles[:, 2]]
                - cropped.points[cropped.triangles[:, 0]],
            ),
            axis=1,
        ).sum()
    )
    assert area == pytest.approx(1.0)
    assert numpy.allclose(cropped.texture_coordinates, cropped.points[:, :2] / 4.0)
    assert numpy.allclose(cropped.normals, [0.0, 0.0, 1.0])


def test_a_mesh_partly_over_the_region_keeps_its_whole_triangles_and_cuts_the_rest():
    mesh = TriangleMesh(
        points=numpy.array(
            [
                [0.1, 0.1, 0.0],
                [0.2, 0.1, 0.0],
                [0.1, 0.2, 0.0],
                [0.5, 0.5, 0.0],
                [3.0, 0.5, 0.0],
                [0.5, 3.0, 0.0],
            ]
        ),
        triangles=numpy.array([[0, 1, 2], [3, 4, 5]], dtype=numpy.uint32),
    )
    cropped = FloorRegion(0.0, 0.0, 1.0, 1.0).crop(mesh, numpy.eye(4))
    assert len(cropped.triangles) >= 2
    assert (cropped.points[:, :2] <= 1.0 + 1e-9).all()
    assert any(numpy.allclose(point, [0.1, 0.1, 0.0]) for point in cropped.points)


def test_a_mesh_wholly_beside_the_region_is_none():
    mesh = TriangleMesh(
        points=numpy.array([[5.0, 5.0, 0.0], [6.0, 5.0, 0.0], [5.0, 6.0, 0.0]]),
        triangles=numpy.array([[0, 1, 2]], dtype=numpy.uint32),
    )
    assert FloorRegion(0.0, 0.0, 1.0, 1.0).crop(mesh, numpy.eye(4)) is None


def test_a_prim_with_nothing_over_the_region_is_skipped_but_keeps_its_collisions():
    region = FloorRegion(100.0, 100.0, 101.0, 101.0)
    plain = StageReader(Stage.SHELF_WITH_TOTES.path).read()
    cropped = StageReader(Stage.SHELF_WITH_TOTES.path, region=region).read()
    assert not any(link.meshes for link in cropped.links)
    assert cropped.log.skipped[SkipReason.OUTSIDE_REGION] > 0
    assert (
        cropped.log.counts[ReportCount.COLLISIONS]
        == plain.log.counts[ReportCount.COLLISIONS]
        > 0
    )


# %% options


STAGE_ARGUMENTS = [str(Stage.GLASS_PANE.path), ImportOption.NAME, "pane"]


def test_the_import_takes_an_origin_and_a_region(tmp_path):
    parser = ImportParser().parser("cramera-import")
    options = parser.parse_args(
        [
            *STAGE_ARGUMENTS,
            ImportOption.ORIGIN,
            "13.6",
            "-2.6",
            "0.1",
            "90",
            ImportOption.REGION,
            "-3",
            "-4",
            "5",
            "4",
        ]
    )
    command = ImportCommand.from_options(options, parser, tmp_path)
    assert command.origin == StageOrigin(13.6, -2.6, 0.1, 90.0)
    assert command.region == FloorRegion(-3.0, -4.0, 5.0, 4.0)


def test_the_import_keeps_the_stage_in_place_without_an_origin(tmp_path):
    parser = ImportParser().parser("cramera-import")
    command = ImportCommand.from_options(
        parser.parse_args(STAGE_ARGUMENTS), parser, tmp_path
    )
    assert command.origin is None and command.region is None


def test_a_region_with_swapped_corners_is_refused(tmp_path):
    parser = ImportParser().parser("cramera-import")
    options = parser.parse_args(
        [*STAGE_ARGUMENTS, ImportOption.REGION, "5", "-4", "-3", "4"]
    )
    with pytest.raises(SystemExit):
        ImportCommand.from_options(options, parser, tmp_path)
