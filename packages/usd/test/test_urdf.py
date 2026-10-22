"""
The URDF written for the links and joints of a converted stage.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree

import numpy
import pytest

from cramera_usd.geometry.meshes import TriangleMesh
from cramera_usd.geometry.transforms import RigidTransform
from cramera_usd.scene.kinematics import AllowedMotion, Joint, JointKind, Link, LinkMesh
from cramera_usd.urdf import UrdfAttribute, UrdfDocument, UrdfTag, XmlEncoding

# %% fixtures


def link(name: str, with_mesh: bool) -> Link:
    """
    :param name: The link name.
    :param with_mesh: Whether the link has visual geometry.
    :return: A link, with or without one triangle.
    """
    meshes = (
        [
            LinkMesh(
                f"/World/{name}/Mesh",
                TriangleMesh(
                    numpy.eye(3, dtype=numpy.float32),
                    numpy.array([[0, 1, 2]], dtype=numpy.uint32),
                ),
                "paint",
            )
        ]
        if with_mesh
        else []
    )
    return Link(name, f"/World/{name}", RigidTransform(), meshes=meshes)


HINGE_ORIGIN = RigidTransform.from_translation_quaternion(
    numpy.array([1.0, 2.0, 3.0]),
    numpy.array([0.0, 0.0, numpy.sin(numpy.pi / 4), numpy.cos(numpy.pi / 4)]),
)
"""
The hinge's frame: shifted and turned a quarter turn about Z.
"""

HINGE = AllowedMotion(JointKind.REVOLUTE, numpy.array([0.0, 0.0, 1.0]), 0.0, 1.5)
"""
The hinge's motion.
"""

SLIDE = AllowedMotion(JointKind.PRISMATIC, numpy.array([1.0, 0.0, 0.0]), None, 0.4)
"""
A slide without a lower limit.
"""


@pytest.fixture()
def document() -> UrdfDocument:
    """
    :return: A root, a door on a hinge, a wheel without limits and a drawer on a slide.
    """
    links = [
        link("World", False),
        link("Door", True),
        link("Wheel", True),
        link("Drawer", True),
    ]
    return UrdfDocument(
        "lab",
        links,
        [
            Joint("Hinge", "/World/Joints/Hinge", HINGE, "World", "Door", HINGE_ORIGIN),
            Joint(
                "Spin",
                "/World/Joints/Spin",
                AllowedMotion(JointKind.CONTINUOUS, numpy.array([0.0, 1.0, 0.0])),
                "World",
                "Wheel",
            ),
            Joint("Slide", "/World/Joints/Slide", SLIDE, "World", "Drawer"),
        ],
        {item.name: f"meshes/{item.name}.glb" for item in links if item.meshes},
    )


def joint_element(document: UrdfDocument, name: str) -> ElementTree.Element:
    """
    :param document: The URDF writer.
    :param name: A joint name.
    :return: The joint element of that name.
    """
    return next(
        element
        for element in document.to_element().iter(UrdfTag.JOINT)
        if element.get(UrdfAttribute.NAME) == name
    )


def numbers(text: str) -> list:
    """
    :param text: An attribute holding numbers.
    :return: The numbers.
    """
    return [float(value) for value in text.split()]


# %% links


def test_links_with_geometry_reference_their_glb(document):
    meshes = {
        element.get(UrdfAttribute.NAME): [
            mesh.get(UrdfAttribute.FILENAME) for mesh in element.iter(UrdfTag.MESH)
        ]
        for element in document.to_element().iter(UrdfTag.LINK)
    }
    assert meshes == {
        item.name: [document.mesh_files[item.name]] if item.meshes else []
        for item in document.links
    }


# %% joints


def test_revolute_joint_writes_origin_axis_and_limits(document):
    element = joint_element(document, "Hinge")
    assert element.get(UrdfAttribute.TYPE) == JointKind.REVOLUTE
    origin = element.find(UrdfTag.ORIGIN)
    assert numbers(origin.get(UrdfAttribute.TRANSLATION)) == pytest.approx(
        HINGE_ORIGIN.translation
    )
    assert numbers(origin.get(UrdfAttribute.ROTATION)) == pytest.approx(
        HINGE_ORIGIN.roll_pitch_yaw
    )
    assert numbers(element.find(UrdfTag.AXIS).get(UrdfAttribute.TRANSLATION)) == list(
        HINGE.axis
    )
    limit = element.find(UrdfTag.LIMIT)
    assert (
        float(limit.get(UrdfAttribute.LOWER)),
        float(limit.get(UrdfAttribute.UPPER)),
    ) == (HINGE.lower, HINGE.upper)


def test_continuous_joint_has_no_position_limits(document):
    limit = joint_element(document, "Spin").find(UrdfTag.LIMIT)
    assert limit.get(UrdfAttribute.LOWER) is None
    assert limit.get(UrdfAttribute.UPPER) is None


def test_missing_slide_limit_becomes_the_unbounded_travel(document):
    limit = joint_element(document, "Slide").find(UrdfTag.LIMIT)
    assert float(limit.get(UrdfAttribute.LOWER)) == -document.unbounded_travel
    assert float(limit.get(UrdfAttribute.UPPER)) == SLIDE.upper


def test_numbers_are_written_without_negative_zeros():
    assert UrdfDocument.numbers([-0.0, 1.5]).split() == ["0", "1.5"]


def test_file_declares_its_encoding(document):
    assert document.to_bytes().startswith(b"<?xml")
    assert XmlEncoding.UTF_8.encode() in document.to_bytes().splitlines()[0]
