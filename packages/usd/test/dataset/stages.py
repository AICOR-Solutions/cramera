"""
The test stages, one per behaviour, and helpers reading them.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import numpy
from pxr import Usd
from typing_extensions import List

from cramera_usd.scene.kinematics import Link
from cramera_usd.scene.stage import ConvertedStage
from cramera_usd.stage.reader import StageReader

# %% directories

DATASET = Path(__file__).parent
"""
The directory holding the test stages.
"""

TEXTURES = DATASET / "textures"
"""
Tiny images whose pixel values the tests compare against.
"""

# %% stages


class Stage(StrEnum):
    """
    The test stages.
    """

    TEXTURED_QUAD = "textured_quad.usda"
    """
    An OmniPBR quad with three textures and semantic attributes.
    """

    GLASS_PANE = "glass_pane.usda"
    """
    A scaled glass pane in a frame.
    """

    Y_UP_CENTIMETRES = "y_up_centimetres.usda"
    """
    A Y-up stage in centimetres with a display-coloured marker.
    """

    INSTANCED_BOLTS = "instanced_bolts.usda"
    """
    Two instances of one bolt.
    """

    HIDDEN_PRIMS = "hidden_prims.usda"
    """
    Guide, proxy, invisible and unsupported prims beside one visible mesh.
    """

    JOINTED_CABINET = "jointed_cabinet.usda"
    """
    A cabinet whose door, drawer, flap and wheel are jointed to its body.
    """

    BODY0_HINGE = "body0_hinge.usda"
    """
    A door hinged to the world by a joint naming only its first body.
    """

    WIDE_HINGE = "wide_hinge.usda"
    """
    A lid opened past half a turn.
    """

    NO_DEFAULT_PRIM = "no_default_prim.usda"
    """
    A stage without a default prim.
    """

    ROBOT_MARKERS = "robot_markers.usda"
    """
    A cell with robots marked both ways and environment prims jointed to them.
    """

    DETACHED_GRIPPER = "detached_gripper.usda"
    """
    A gripper the stage puts beside its marked robot.
    """

    UNMARKED_ARTICULATION = "unmarked_articulation.usda"
    """
    An unmarked robot, a marked one and environment articulations.
    """

    LIT_ROOM = "lit_room.usda"
    """
    A room with a sun, a dome, a ceiling panel and a camera.
    """

    SPHERICAL_JOINT = "spherical_joint.usda"
    """
    A joint type URDF has no counterpart for.
    """

    TWO_JOINT_ARM = "two_joint_arm.usda"
    """
    An animated two-joint arm whose joints exist only in its physics variant.
    """

    ANNOTATED_LAB = "annotated_lab.usda"
    """
    A lab with ontology and twin attributes.
    """

    @property
    def path(self) -> Path:
        """
        The stage file.
        """
        return DATASET / self.value


# %% reading


def read(stage: Stage, *prim_paths: str) -> ConvertedStage:
    """
    :param stage: A test stage.
    :param prim_paths: The selected prims, none for the whole stage.
    :return: Its converted description.
    """
    return StageReader(stage.path, list(prim_paths)).read()


def open_stage(stage: Stage) -> Usd.Stage:
    """
    :param stage: A test stage.
    :return: The composed stage, to read authored values for comparison.
    """
    return Usd.Stage.Open(str(stage.path))


# %% link geometry


def world_points(link: Link, path: str) -> numpy.ndarray:
    """
    :param link: The link holding a prim's mesh.
    :param path: The prim path.
    :return: The world positions of the mesh's vertices.
    """
    mesh = next(mesh for mesh in link.meshes if mesh.path == path)
    return mesh.geometry.points @ link.pose.rotation.T + link.pose.translation


def link_holding(converted: ConvertedStage, path: str) -> Link:
    """
    :param converted: A converted stage.
    :param path: A geometry prim's path.
    :return: The link holding the prim's mesh.
    """
    return next(
        link
        for link in converted.links
        if any(mesh.path == path for mesh in link.meshes)
    )


def mesh_paths(converted: ConvertedStage) -> set:
    """
    :param converted: A converted stage.
    :return: The prims whose geometry the stage holds.
    """
    return {mesh.path for link in converted.links for mesh in link.meshes}


# %% joints


def reproduces_link_frames(converted: ConvertedStage) -> bool:
    """
    :param converted: A converted stage.
    :return: Whether every joint, moved to its initial value, places its child link
        where the stage put it.
    """
    links = {link.name: link for link in converted.links}
    return all(
        (
            links[joint.parent].pose
            @ joint.origin
            @ joint.motion.transform(joint.initial_value)
        ).is_close(links[joint.child].pose)
        for joint in converted.joints
    )


def authored_joint_paths(converted: ConvertedStage) -> set:
    """
    :param converted: A converted stage.
    :return: The joint prims the stage converted, without the generated attachments.
    """
    return {joint.path for joint in converted.joints if not joint.generated}


# %% paths


def lies_in(path: str, subtrees: List[str]) -> bool:
    """
    :param path: A prim path.
    :param subtrees: Subtree root paths.
    :return: Whether the prim lies in one of the subtrees.
    """
    return any(path == root or path.startswith(root + "/") for root in subtrees)
