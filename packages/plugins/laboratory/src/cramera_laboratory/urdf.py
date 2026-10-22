"""
The URDF vocabulary the laboratory reads.
"""

from __future__ import annotations

from enum import StrEnum

# %% names


class UrdfTag(StrEnum):
    """
    The URDF elements the model reads.
    """

    LINK = "link"
    """
    The ``link`` element.
    """

    JOINT = "joint"
    """
    The ``joint`` element.
    """

    COLLISION = "collision"
    """
    The ``collision`` element.
    """

    GEOMETRY = "geometry"
    """
    The ``geometry`` element.
    """

    ORIGIN = "origin"
    """
    The ``origin`` element.
    """

    INERTIAL = "inertial"
    """
    The ``inertial`` element.
    """

    MASS = "mass"
    """
    The ``mass`` element.
    """

    INERTIA = "inertia"
    """
    The ``inertia`` element.
    """

    PARENT = "parent"
    """
    The ``parent`` element.
    """

    CHILD = "child"
    """
    The ``child`` element.
    """

    AXIS = "axis"
    """
    The ``axis`` element.
    """

    LIMIT = "limit"
    """
    The ``limit`` element.
    """

    DYNAMICS = "dynamics"
    """
    The ``dynamics`` element.
    """

    BOX = "box"
    """
    The ``box`` element.
    """

    CYLINDER = "cylinder"
    """
    The ``cylinder`` element.
    """

    SPHERE = "sphere"
    """
    The ``sphere`` element.
    """

    MESH = "mesh"
    """
    The ``mesh`` element.
    """


class UrdfAttribute(StrEnum):
    """
    The URDF attributes the model reads.
    """

    NAME = "name"
    """
    The ``name`` attribute.
    """

    TYPE = "type"
    """
    The ``type`` attribute.
    """

    LINK = "link"
    """
    The ``link`` attribute.
    """

    XYZ = "xyz"
    """
    The ``xyz`` attribute.
    """

    RPY = "rpy"
    """
    The ``rpy`` attribute.
    """

    VALUE = "value"
    """
    The ``value`` attribute.
    """

    SIZE = "size"
    """
    The ``size`` attribute.
    """

    RADIUS = "radius"
    """
    The ``radius`` attribute.
    """

    LENGTH = "length"
    """
    The ``length`` attribute.
    """

    FILENAME = "filename"
    """
    The ``filename`` attribute.
    """

    SCALE = "scale"
    """
    The ``scale`` attribute.
    """

    LOWER = "lower"
    """
    The ``lower`` attribute.
    """

    UPPER = "upper"
    """
    The ``upper`` attribute.
    """

    EFFORT = "effort"
    """
    The ``effort`` attribute.
    """

    DAMPING = "damping"
    """
    The ``damping`` attribute.
    """

    FRICTION = "friction"
    """
    The ``friction`` attribute.
    """


class UrdfJointType(StrEnum):
    """
    The URDF joint types the model distinguishes.
    """

    FIXED = "fixed"
    """
    The ``fixed`` joint type.
    """

    REVOLUTE = "revolute"
    """
    The ``revolute`` joint type.
    """

    CONTINUOUS = "continuous"
    """
    The ``continuous`` joint type.
    """

    PRISMATIC = "prismatic"
    """
    The ``prismatic`` joint type.
    """

    FLOATING = "floating"
    """
    The ``floating`` joint type.
    """
