"""
Triangle meshes of USD's implicit shapes: cube, sphere, cylinder, cone and capsule.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy

from cramera_usd.geometry.axes import Axis
from cramera_usd.geometry.meshes import TriangleMesh
from cramera_usd.geometry.transforms import (
    FULL_TURN,
    HOMOGENEOUS_SIZE,
    SPACE_DIMENSIONS,
)

# %% constants

QUARTER_TURN = numpy.pi / 2.0
"""
A quarter turn in radians.
"""

QUAD_CORNERS = ((-1, -1), (1, -1), (1, 1), (-1, 1))
"""
The corners of a square face as multiples of its two edge directions, counter-clockwise.
"""

# %% profiles


@dataclass(frozen=True, eq=False)
class LatheProfile:
    """
    A profile to revolve about the Z axis: radius and height of each point, with the
    radial and vertical normal components there.
    """

    points: numpy.ndarray
    """
    ``(P, 2)`` radius and height, from the bottom to the top.
    """

    normals: numpy.ndarray
    """
    ``(P, 2)`` radial and vertical normal components.
    """

    def revolved(self, segments: int) -> TriangleMesh:
        """
        :param segments: The subdivisions around the axis.
        :return: The surface swept by the profile; consecutive equal profile points form
            a crease and are not bridged.
        """
        angles = numpy.linspace(0.0, FULL_TURN, segments + 1)
        cosine, sine = numpy.cos(angles), numpy.sin(angles)
        ring = segments + 1
        triangles = []
        for level in range(len(self.points) - 1):
            if numpy.allclose(self.points[level], self.points[level + 1]):
                continue
            for step in range(segments):
                lower_start = level * ring + step
                lower_end = lower_start + 1
                upper_end, upper_start = lower_end + ring, lower_start + ring
                triangles += [
                    (lower_start, lower_end, upper_end),
                    (lower_start, upper_end, upper_start),
                ]
        return TriangleMesh(
            self.swept(self.points, cosine, sine, ring),
            numpy.array(triangles, numpy.uint32),
            self.swept(self.normals, cosine, sine, ring),
        )

    @staticmethod
    def swept(
        values: numpy.ndarray, cosine: numpy.ndarray, sine: numpy.ndarray, ring: int
    ) -> numpy.ndarray:
        """
        :param values: ``(P, 2)`` radial and vertical components.
        :param cosine: The cosine of every angle around the axis.
        :param sine: The sine of every angle around the axis.
        :param ring: The number of vertices per profile point.
        :return: ``(P * ring, 3)`` vectors, one per profile point and angle.
        """
        return numpy.stack(
            [
                numpy.outer(values[:, 0], cosine).ravel(),
                numpy.outer(values[:, 0], sine).ravel(),
                numpy.repeat(values[:, 1], ring),
            ],
            axis=1,
        )


# %% shapes


@dataclass
class ShapeTessellation:
    """
    Triangle meshes for USD's implicit shapes, centred on the origin as USD defines
    them.
    """

    segments: int = 32
    """
    Subdivisions around the axis of a round shape.
    """

    rings: int = 16
    """
    Subdivisions from pole to pole of a sphere (half of that per capsule cap).
    """

    def box(self, size: float) -> TriangleMesh:
        """
        :param size: The edge length.
        :return: A cube with one flat normal per face.
        """
        points, normals, triangles = [], [], []
        for axis in range(SPACE_DIMENSIONS):
            for sign in (-1.0, 1.0):
                normal = numpy.zeros(SPACE_DIMENSIONS)
                normal[axis] = sign
                first = numpy.roll(normal, 1) * sign
                second = numpy.cross(normal, first)
                base = len(points)
                for along, across in QUAD_CORNERS:
                    points.append((normal + along * first + across * second) * size / 2)
                    normals.append(normal)
                triangles += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
        return TriangleMesh(
            numpy.array(points),
            numpy.array(triangles, numpy.uint32),
            numpy.array(normals),
        )

    def sphere(self, radius: float) -> TriangleMesh:
        """
        :param radius: The radius.
        :return: A sphere.
        """
        latitude = numpy.linspace(-QUARTER_TURN, QUARTER_TURN, self.rings + 1)
        directions = numpy.stack([numpy.cos(latitude), numpy.sin(latitude)], axis=1)
        return LatheProfile(directions * radius, directions).revolved(self.segments)

    def cylinder(self, radius: float, height: float, axis: Axis) -> TriangleMesh:
        """
        :param radius: The radius.
        :param height: The length along the axis.
        :param axis: The axis.
        :return: A capped cylinder.
        """
        half = height / 2
        profile = numpy.array(
            [
                [0, -half],
                [radius, -half],
                [radius, -half],
                [radius, half],
                [radius, half],
                [0, half],
            ],
            dtype=float,
        )
        normals = numpy.array(
            [[0, -1], [0, -1], [1, 0], [1, 0], [0, 1], [0, 1]], dtype=float
        )
        return self.oriented(LatheProfile(profile, normals), axis)

    def cone(self, radius: float, height: float, axis: Axis) -> TriangleMesh:
        """
        :param radius: The base radius.
        :param height: The length along the axis.
        :param axis: The axis.
        :return: A capped cone with its apex on the positive side of the axis.
        """
        half = height / 2
        side = numpy.array([height, radius]) / numpy.hypot(height, radius)
        profile = numpy.array(
            [[0, -half], [radius, -half], [radius, -half], [0, half]], dtype=float
        )
        normals = numpy.array([[0, -1], [0, -1], side, side], dtype=float)
        return self.oriented(LatheProfile(profile, normals), axis)

    def capsule(self, radius: float, height: float, axis: Axis) -> TriangleMesh:
        """
        :param radius: The radius.
        :param height: The length of the cylindrical part, without the caps.
        :param axis: The axis.
        :return: A cylinder with hemispherical caps.
        """
        half_rings = max(self.rings // 2, 1)
        lower = numpy.linspace(-QUARTER_TURN, 0.0, half_rings + 1)
        upper = numpy.linspace(0.0, QUARTER_TURN, half_rings + 1)
        directions = numpy.concatenate(
            [
                numpy.stack([numpy.cos(lower), numpy.sin(lower)], axis=1),
                numpy.stack([numpy.cos(upper), numpy.sin(upper)], axis=1),
            ]
        )
        offsets = numpy.concatenate(
            [
                numpy.full(half_rings + 1, -height / 2),
                numpy.full(half_rings + 1, height / 2),
            ]
        )
        profile = directions * radius + numpy.stack(
            [numpy.zeros_like(offsets), offsets], axis=1
        )
        return self.oriented(LatheProfile(profile, directions), axis)

    def oriented(self, profile: LatheProfile, axis: Axis) -> TriangleMesh:
        """
        :param profile: The profile of a shape around Z.
        :param axis: The axis the shape is built around.
        :return: The revolved shape turned onto the axis.
        """
        rotation = numpy.eye(HOMOGENEOUS_SIZE)
        rotation[:SPACE_DIMENSIONS, :SPACE_DIMENSIONS] = axis.rotation_from_z()
        return profile.revolved(self.segments).transformed(rotation)
