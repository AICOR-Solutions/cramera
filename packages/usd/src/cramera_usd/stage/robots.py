"""
The robots a stage marks, and the prims a conversion leaves out with their subtrees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pxr import Sdf, Usd
from typing_extensions import List, Optional

from cramera_protocol.bundle.conversion_report import ExcludedPrim, ExclusionReason
from cramera_protocol.bundle.semantics import SemanticNamespace
from cramera_usd.exceptions import PrimNotFound, RobotExcluded, SelectedPrimLeftOut

# %% marks


class RobotMarker(StrEnum):
    """
    How a stage marks the root prim of a robot, spelled as the stage spells it.
    """

    ISAAC_ROBOT_SCHEMA = "IsaacRobotAPI"
    """
    The API schema of Isaac Sim's robot schema (``isaacsim.robot.schema``), applied to
    the root prim.
    """

    ROBOT_ENTITY_TYPE = "Robot"
    """
    The semantic entity type of a robot's root prim; only this exact value marks a
    robot.
    """


class SemanticAttributeName(StrEnum):
    """
    The twin attributes the converter reads by name, without their namespace.
    """

    ENTITY_TYPE = "entityType"
    """
    The kind of entity the prim stands for.
    """


ENTITY_TYPE_ATTRIBUTE = Sdf.Path.JoinIdentifier(
    [
        SemanticNamespace.SEMANTIC_DIGITAL_TWIN.value,
        SemanticAttributeName.ENTITY_TYPE.value,
    ]
)
"""
The full name of the entity type attribute, ``sdt:entityType``.
"""


@dataclass(frozen=True)
class RobotMarks:
    """
    Reads the marks by which a stage declares a prim the root of a robot.
    """

    time: Usd.TimeCode = field(default_factory=Usd.TimeCode.Default)
    """
    The time the stage is read at.
    """

    def mark_of(self, prim: Usd.Prim) -> Optional[ExclusionReason]:
        """
        .. note:: The authored schema list is read because USD leaves a schema it has
            no definition for, such as Isaac Sim's robot schema in usd-core, out of the
            applied schemas.

        :param prim: A prim.
        :return: The reason the prim's mark gives to leave it out as a robot, or None
            for a prim that is not marked.
        """
        if (
            RobotMarker.ISAAC_ROBOT_SCHEMA
            in prim.GetPrimTypeInfo().GetAppliedAPISchemas()
        ):
            return ExclusionReason.ISAAC_ROBOT_SCHEMA
        if self.has_entity_type(prim):
            return ExclusionReason.ROBOT_ENTITY_TYPE
        return None

    def has_entity_type(self, prim: Usd.Prim) -> bool:
        """
        :param prim: A prim.
        :return: Whether the prim's entity type marks it as a robot.
        """
        entity_type = prim.GetAttribute(ENTITY_TYPE_ATTRIBUTE)
        return bool(entity_type) and (
            entity_type.Get(self.time) == RobotMarker.ROBOT_ENTITY_TYPE
        )


# %% exclusion


@dataclass
class PrimExclusion:
    """
    Which prims a conversion leaves out together with their subtrees: the excluded
    prims, and the robots the stage marks unless they are kept.
    """

    excluded_paths: List[str] = field(default_factory=list)
    """
    The prims left out on request.
    """

    keep_robots: bool = False
    """
    Whether the robots the stage marks are converted with the environment.
    """

    robot_path: Optional[str] = None
    """
    The prim of the robot converted as a model of its own, or None; a marked robot
    holding this prim or lying below it is kept.
    """

    def validate(
        self, stage: Usd.Stage, roots: List[Usd.Prim], time: Usd.TimeCode
    ) -> None:
        """
        Refuse an excluded prim the stage does not have, a kept robot inside an excluded
        prim, and a selected prim inside a prim the conversion leaves out.

        :param stage: The composed stage.
        :param roots: The prims whose subtrees are converted.
        :param time: The time the stage is read at.
        :raises PrimNotFound: When an excluded prim does not exist.
        :raises RobotExcluded: When the kept robot lies in an excluded prim.
        :raises SelectedPrimLeftOut: When a selected prim lies in a left-out prim.
        """
        for path in self.excluded_paths:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsActive():
                raise PrimNotFound(path)
            if self.robot_path is not None and Sdf.Path(self.robot_path).HasPrefix(
                Sdf.Path(path)
            ):
                raise RobotExcluded(self.robot_path, path)
        for root in roots:
            if root.IsPseudoRoot():
                continue
            left_out = self.left_out_holding(stage, root.GetPath(), time)
            if left_out is not None:
                raise SelectedPrimLeftOut(root.GetPath().pathString, left_out)

    def left_out_holding(
        self, stage: Usd.Stage, path: Sdf.Path, time: Usd.TimeCode
    ) -> Optional[ExcludedPrim]:
        """
        :param stage: The composed stage.
        :param path: The USD path of a prim; only the ancestors the stage has count.
        :param time: The time the stage is read at.
        :return: The outermost of the prim and its ancestors that the conversion leaves
            out, and why, or None when the prim is converted.
        """
        for prefix in path.GetPrefixes():
            prim = stage.GetPrimAtPath(prefix)
            if not prim:
                return None
            reason = self.reason_to_leave_out(prim, time)
            if reason is not None:
                return ExcludedPrim(path=prefix.pathString, reason=reason)
        return None

    def belongs_to_robot(
        self, stage: Usd.Stage, path: Sdf.Path, time: Usd.TimeCode
    ) -> bool:
        """
        :param stage: The composed stage.
        :param path: The USD path of a prim.
        :param time: The time the stage is read at.
        :return: Whether the prim is or lies in a robot the stage marks, or is, holds or
            lies in the kept robot.
        """
        if self.holds_kept_robot(path):
            return True
        marks = RobotMarks(time)
        return any(
            marks.mark_of(stage.GetPrimAtPath(prefix)) is not None
            for prefix in path.GetPrefixes()
        )

    def reason_to_leave_out(
        self, prim: Usd.Prim, time: Usd.TimeCode
    ) -> Optional[ExclusionReason]:
        """
        :param prim: A prim.
        :param time: The time the stage is read at.
        :return: Why the prim is left out together with its subtree, or None when it is
            converted.
        """
        path = prim.GetPath()
        if any(path.HasPrefix(Sdf.Path(excluded)) for excluded in self.excluded_paths):
            return ExclusionReason.REQUESTED
        if self.keep_robots or self.holds_kept_robot(path):
            return None
        return RobotMarks(time).mark_of(prim)

    def holds_kept_robot(self, path: Sdf.Path) -> bool:
        """
        :param path: A prim path.
        :return: Whether the prim is the kept robot's prim, lies above it or lies below
            it.
        """
        if self.robot_path is None:
            return False
        robot = Sdf.Path(self.robot_path)
        return robot.HasPrefix(path) or path.HasPrefix(robot)
