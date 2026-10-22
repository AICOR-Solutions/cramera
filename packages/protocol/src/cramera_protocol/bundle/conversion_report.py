"""
The conversion report, ``conversion_report.json``: what a conversion of a stage read,
wrote and left out.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Dict, List, Optional

from cramera_protocol.document import JsonDocument, document_field

# %% reasons


class ExclusionReason(StrEnum):
    """
    Why a prim was left out of a conversion together with its subtree.
    """

    REQUESTED = "requested"
    """
    The prim was named to be left out.
    """

    ISAAC_ROBOT_SCHEMA = "Isaac robot schema"
    """
    The prim is a robot: Isaac Sim's robot schema is applied to it.
    """

    ROBOT_ENTITY_TYPE = "robot entity type"
    """
    The prim is a robot: its semantic entity type says so.
    """


class SkipReason(StrEnum):
    """
    Why a prim was left out of the converted visuals or joints.
    """

    GUIDE_PURPOSE = "guide purpose"
    """
    The prim is guide geometry, such as a collision proxy.
    """

    PROXY_PURPOSE = "proxy purpose"
    """
    The prim is a lightweight stand-in for render geometry.
    """

    INVISIBLE = "invisible"
    """
    The prim or one of its ancestors is invisible.
    """

    UNSUPPORTED_GEOMETRY = "unsupported geometry type"
    """
    The prim is renderable geometry of a type the converter cannot tessellate.
    """

    EMPTY_GEOMETRY = "empty geometry"
    """
    The prim has no faces.
    """

    LOOP_CLOSING_JOINT = "loop-closing joint"
    """
    The joint would give a link a second parent; URDF describes trees only.
    """

    JOINT_WITHOUT_CHILD = "joint without child body"
    """
    The joint names no body to move.
    """

    JOINT_TO_EXCLUDED_PRIM = "joint to an excluded prim"
    """
    One of the joint's bodies lies in a subtree the conversion leaves out.
    """


COUNT_KEY_SEPARATOR = "."
"""
The separator between a count and the joint type it is counted for.
"""


class ReportCount(StrEnum):
    """
    The named counts of a conversion report.
    """

    PRIMS = "prims"
    """
    Prims traversed.
    """

    INSTANCE_PROXIES = "instanceProxies"
    """
    Traversed prims that are instance proxies.
    """

    LINKS = "links"
    """
    Links written.
    """

    MESHES = "meshes"
    """
    Meshes written, one per geometry prim and material.
    """

    TRIANGLES = "triangles"
    """
    Triangles written.
    """

    MATERIALS = "materials"
    """
    Distinct materials bound.
    """

    LIGHTS = "lights"
    """
    Lights read.
    """

    SEMANTIC_PRIMS = "semanticPrims"
    """
    Prims carrying semantic attributes.
    """

    JOINTS = "joints"
    """
    Joints written, counted per joint type as ``joints.<type>``.
    """

    DISABLED_JOINTS = "disabledJoints"
    """
    Joints written although disabled for the simulation.
    """

    def of_type(self, joint_type: str) -> str:
        """
        :param joint_type: A URDF joint type, such as ``revolute``.
        :return: The count key of that joint type, such as ``joints.revolute``.
        """
        return f"{self.value}{COUNT_KEY_SEPARATOR}{joint_type}"


# %% left-out prims


class ExcludedPrimKey(StrEnum):
    """
    The keys of one prim left out with its subtree.
    """

    PATH = "path"
    """
    The prim's USD path.
    """

    REASON = "reason"
    """
    Why it was left out.
    """


@dataclass(kw_only=True)
class ExcludedPrim(JsonDocument):
    """
    A prim a conversion left out together with its subtree.
    """

    path: str = document_field(ExcludedPrimKey.PATH)
    """
    The USD path of the prim.
    """

    reason: ExclusionReason = document_field(ExcludedPrimKey.REASON)
    """
    Why it was left out.
    """


class DetachedBodyKey(StrEnum):
    """
    The keys of one body whose joint to a left-out body was dropped.
    """

    BODY = "body"
    """
    The body's USD path.
    """

    PARENT_BODY = "parentBody"
    """
    The USD path of the left-out body it hung from.
    """

    JOINT = "joint"
    """
    The USD path of the dropped joint.
    """

    MOVABLE_JOINTS = "movableJoints"
    """
    The USD paths of the movable joints below the body.
    """


@dataclass(kw_only=True)
class DetachedBody(JsonDocument):
    """
    A converted body whose joint to a left-out parent body was dropped: it stays at its
    authored pose, held by the world instead.
    """

    body: str = document_field(DetachedBodyKey.BODY)
    """
    The USD path of the converted body.
    """

    parent_body: str = document_field(DetachedBodyKey.PARENT_BODY)
    """
    The USD path of the left-out body it hung from.
    """

    joint: str = document_field(DetachedBodyKey.JOINT)
    """
    The USD path of the dropped joint.
    """

    movable_joints: List[str] = document_field(
        DetachedBodyKey.MOVABLE_JOINTS, default_factory=list
    )
    """
    The USD paths of the converted movable joints that move parts hanging from the body;
    a body with any is more likely a part of a robot than an object it held.
    """


class ArticulationKey(StrEnum):
    """
    The keys of one articulation converted with the environment.
    """

    PATH = "path"
    """
    The USD path of the articulation root.
    """

    MOVABLE_JOINTS = "movableJoints"
    """
    The USD paths of its movable joints.
    """


@dataclass(kw_only=True)
class EnvironmentArticulation(JsonDocument):
    """
    An articulation root converted as part of the environment, outside every robot the
    stage marks: a door or station, or a robot the stage does not mark.
    """

    path: str = document_field(ArticulationKey.PATH)
    """
    The USD path of the prim carrying the articulation root.
    """

    movable_joints: List[str] = document_field(
        ArticulationKey.MOVABLE_JOINTS, default_factory=list
    )
    """
    The USD paths of the converted movable joints of the articulation.
    """


# %% playback


class AnimationSummaryKey(StrEnum):
    """
    The keys of the report's summary of a converted playback.
    """

    SOURCE = "source"
    """
    Where the body poses were recorded or sampled.
    """

    FRAME_COUNT = "frameCount"
    """
    The number of playback frames.
    """

    FRAMES_PER_SECOND = "framesPerSecond"
    """
    The playback rate.
    """

    LARGEST_BODY_DISTANCE = "largestBodyDistanceMillimetres"
    """
    The largest position error of a replayed body.
    """

    LARGEST_BODY_ANGLE = "largestBodyAngleDegrees"
    """
    The largest orientation error of a replayed body.
    """

    BEYOND_TOLERANCE = "beyondTolerance"
    """
    The bodies and joints whose residuals exceed the tolerance.
    """

    OBJECTS = "objects"
    """
    The keys of the objects played back by their poses.
    """

    UNTRACKED_BODIES = "untrackedBodies"
    """
    Recorded bodies no link stands for.
    """


@dataclass(kw_only=True)
class AnimationSummary(JsonDocument):
    """
    What a converted playback holds and how well it reproduces its recording.
    """

    source: str = document_field(AnimationSummaryKey.SOURCE)
    """
    The trace file or stage the body poses come from.
    """

    frame_count: int = document_field(AnimationSummaryKey.FRAME_COUNT)
    """
    The number of playback frames.
    """

    frames_per_second: float = document_field(AnimationSummaryKey.FRAMES_PER_SECOND)
    """
    The playback rate.
    """

    largest_body_distance: float = document_field(
        AnimationSummaryKey.LARGEST_BODY_DISTANCE
    )
    """
    The largest position error of a replayed body in millimetres.
    """

    largest_body_angle: float = document_field(AnimationSummaryKey.LARGEST_BODY_ANGLE)
    """
    The largest orientation error of a replayed body in degrees.
    """

    beyond_tolerance: List[str] = document_field(
        AnimationSummaryKey.BEYOND_TOLERANCE, default_factory=list
    )
    """
    The USD paths of the bodies and joints whose residuals exceed the tolerance.
    """

    objects: List[str] = document_field(
        AnimationSummaryKey.OBJECTS, default_factory=list
    )
    """
    The keys of the objects played back by their poses.
    """

    untracked_bodies: List[str] = document_field(
        AnimationSummaryKey.UNTRACKED_BODIES, default_factory=list
    )
    """
    The USD paths of recorded bodies no link stands for.
    """


# %% report


class ConversionReportKey(StrEnum):
    """
    The keys of ``conversion_report.json``.
    """

    SOURCE = "source"
    """
    The converted stage.
    """

    CONVERTER = "converter"
    """
    The version of the converter.
    """

    READ_SECONDS = "readSeconds"
    """
    How long reading the stage took.
    """

    WRITE_SECONDS = "writeSeconds"
    """
    How long writing the bundle took.
    """

    BUNDLE_BYTES = "bundleBytes"
    """
    The size of the bundle on disk.
    """

    COUNTS = "counts"
    """
    The named counts.
    """

    SKIPPED = "skipped"
    """
    The number of prims left out, per reason.
    """

    SKIPPED_EXAMPLES = "skippedExamples"
    """
    A few prims left out, per reason.
    """

    EXCLUDED = "excluded"
    """
    The prims left out together with their subtrees.
    """

    DETACHED = "detached"
    """
    The bodies whose joint to a left-out body was dropped.
    """

    ARTICULATIONS = "articulations"
    """
    The articulations with movable joints converted outside every marked robot.
    """

    UNMAPPED_INPUTS = "unmappedInputs"
    """
    The shader inputs no mapping carried over, per material.
    """

    MISSING_TEXTURES = "missingTextures"
    """
    Texture paths that did not resolve to a file.
    """

    WARNINGS = "warnings"
    """
    Everything else worth a look.
    """

    ANIMATION = "animation"
    """
    The summary of the playback.
    """


@dataclass(kw_only=True)
class ConversionReport(JsonDocument):
    """
    The content of ``conversion_report.json``.
    """

    source: str = document_field(ConversionReportKey.SOURCE)
    """
    The path of the converted stage.
    """

    converter: str = document_field(ConversionReportKey.CONVERTER)
    """
    The version of the converter that wrote the bundle.
    """

    read_seconds: float = document_field(ConversionReportKey.READ_SECONDS)
    """
    How long reading the stage took, in seconds.
    """

    write_seconds: float = document_field(ConversionReportKey.WRITE_SECONDS)
    """
    How long writing the bundle took, in seconds.
    """

    bundle_bytes: int = document_field(ConversionReportKey.BUNDLE_BYTES)
    """
    The size of the bundle's other files on disk, in bytes.
    """

    counts: Dict[str, int] = document_field(
        ConversionReportKey.COUNTS, default_factory=dict
    )
    """
    The named counts of what was read and written, by :class:`ReportCount` key.
    """

    skipped: Dict[str, int] = document_field(
        ConversionReportKey.SKIPPED, default_factory=dict
    )
    """
    The number of prims left out, by :class:`SkipReason` value.
    """

    skipped_examples: Dict[str, List[str]] = document_field(
        ConversionReportKey.SKIPPED_EXAMPLES, default_factory=dict
    )
    """
    A few USD paths of the prims left out, by :class:`SkipReason` value.
    """

    excluded: List[ExcludedPrim] = document_field(
        ConversionReportKey.EXCLUDED, default_factory=list
    )
    """
    The prims left out with their subtrees, in traversal order.
    """

    detached: List[DetachedBody] = document_field(
        ConversionReportKey.DETACHED, default_factory=list
    )
    """
    The converted bodies whose joint to a left-out parent body was dropped.
    """

    articulations: List[EnvironmentArticulation] = document_field(
        ConversionReportKey.ARTICULATIONS, default_factory=list
    )
    """
    The articulations with movable joints converted outside every marked robot.
    """

    unmapped_inputs: Dict[str, List[str]] = document_field(
        ConversionReportKey.UNMAPPED_INPUTS, default_factory=dict
    )
    """
    The authored shader inputs no mapping carried over, by material.
    """

    missing_textures: List[str] = document_field(
        ConversionReportKey.MISSING_TEXTURES, default_factory=list
    )
    """
    The texture asset paths that did not resolve to a file.
    """

    warnings: List[str] = document_field(
        ConversionReportKey.WARNINGS, default_factory=list
    )
    """
    Everything else worth a look.
    """

    animation: Optional[AnimationSummary] = document_field(
        ConversionReportKey.ANIMATION, default=None
    )
    """
    The summary of the playback, or None for a bundle without one.
    """
