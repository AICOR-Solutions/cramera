"""
The checks of how a composed twin stage separates its robots from its environment.

A robot root is the outermost prim the stage marks as a robot (see
:class:`~cramera_usd.stage.robots.RobotMarks`), the prims ``cramera-import`` leaves out
by default.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path

from pxr import Sdf, Usd, UsdGeom, UsdPhysics
from typing_extensions import List

from cramera_usd.audit.report import AuditCheckName, AuditDetail, AuditLine
from cramera_usd.stage.robots import ENTITY_TYPE_ATTRIBUTE, RobotMarker, RobotMarks

# %% twin layers


class TwinLayer(StrEnum):
    """
    The layers a twin's root layer composes, named after the part of the twin they hold.
    """

    ROBOTS = "robots"
    """
    The robots, in the robots scope.
    """

    ENVIRONMENT = "environment"
    """
    Everything else.
    """


LAYER_NAME_SEPARATOR = "_"
"""
Between the twin's stage name and the part a layer holds.
"""

LAYER_SUFFIX = ".usda"
"""
The suffix of a twin's layers.
"""

DEFAULT_ROBOTS_SCOPE = "/World/Robots"
"""
The scope holding a twin's robots.
"""

# %% audited stage


@dataclass
class AuditedTwin:
    """
    A composed twin stage, with its robot roots and the layers it should compose.
    """

    path: Path
    """
    The root layer of the stage.
    """

    stage: Usd.Stage
    """
    The composed stage.
    """

    scope: Sdf.Path
    """
    The scope holding the robots.
    """

    without_robots: bool = False
    """
    Whether the twin is declared to have no robots.
    """

    @cached_property
    def roots(self) -> List[Usd.Prim]:
        """
        The outermost marked prims; a mark inside a robot, such as an imported gripper,
        belongs to that robot.
        """
        marks = RobotMarks()
        roots = []
        iterator = iter(
            Usd.PrimRange(
                self.stage.GetPseudoRoot(),
                Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate),
            )
        )
        for prim in iterator:
            if not prim.IsPseudoRoot() and marks.mark_of(prim) is not None:
                roots.append(prim)
                iterator.PruneChildren()
        return roots

    @property
    def root_paths(self) -> List[Sdf.Path]:
        """
        The paths of the robot roots.
        """
        return [root.GetPath() for root in self.roots]

    def layer_file(self, layer: TwinLayer) -> Path:
        """
        :param layer: A part of the twin.
        :return: The layer file that should hold it, next to the root layer.
        """
        return self.path.with_name(
            f"{self.path.stem}{LAYER_NAME_SEPARATOR}{layer}{LAYER_SUFFIX}"
        )

    def in_robots(self, path: Sdf.Path) -> bool:
        """
        :param path: A prim path.
        :return: Whether the prim lies in the robots scope or in a robot root.
        """
        return any(path.HasPrefix(robot) for robot in [self.scope, *self.root_paths])


# %% checks


class SeparationCheck(ABC):
    """
    One check of the audit.
    """

    @abstractmethod
    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        """
        :param twin: The audited twin.
        :return: The check's outcome.
        """


@dataclass(frozen=True)
class MarkedRobots(SeparationCheck):
    """
    R0: the stage marks at least one robot root, or none for a twin without robots.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        if twin.without_robots:
            return AuditLine(
                check=AuditCheckName.MARKED_ROBOTS,
                passed=not twin.roots,
                what="a twin without robots marks no robot root",
                details={AuditDetail.ROOTS: [str(path) for path in twin.root_paths]},
            )
        return AuditLine(
            check=AuditCheckName.MARKED_ROBOTS,
            passed=bool(twin.roots),
            what="the stage marks at least one robot root",
            details={AuditDetail.COUNT: len(twin.roots)},
        )


@dataclass(frozen=True)
class LayersComposed(SeparationCheck):
    """
    R1: the root layer sublayers the robots and environment layers next to it, and both
    resolve.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        layer = twin.stage.GetRootLayer()
        sublayers = {
            os.path.normpath(layer.ComputeAbsolutePath(path))
            for path in layer.subLayerPaths
        }
        wanted = [twin.layer_file(part) for part in TwinLayer]
        missing = [
            file.name
            for file in wanted
            if str(file) not in sublayers or not file.is_file()
        ]
        return AuditLine(
            check=AuditCheckName.LAYERS_COMPOSED,
            passed=not missing,
            what=f"root layer sublayers {' and '.join(file.name for file in wanted)}",
            details={
                AuditDetail.MISSING: missing,
                AuditDetail.SUBLAYERS: list(layer.subLayerPaths),
            },
        )


@dataclass(frozen=True)
class RobotsInScope(SeparationCheck):
    """
    R2: every robot root is a direct child of the robots scope.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        outside = [
            str(path) for path in twin.root_paths if path.GetParentPath() != twin.scope
        ]
        return AuditLine(
            check=AuditCheckName.ROBOTS_IN_SCOPE,
            passed=not outside,
            what=f"every robot root is a child of {twin.scope}",
            details={AuditDetail.OUTSIDE: outside},
        )


@dataclass(frozen=True)
class ScopeHoldsRobotsOnly(SeparationCheck):
    """
    R3: every child of the robots scope is a robot root; mounts, rails and docks belong
    elsewhere.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        scope = twin.stage.GetPrimAtPath(twin.scope)
        children = scope.GetChildren() if scope else []
        foreign = [
            str(child.GetPath())
            for child in children
            if child.GetPath() not in twin.root_paths
        ]
        return AuditLine(
            check=AuditCheckName.SCOPE_HOLDS_ROBOTS_ONLY,
            passed=(bool(scope) or twin.without_robots) and not foreign,
            what=f"every child of {twin.scope} is a robot root",
            details={
                AuditDetail.SCOPE_EXISTS: bool(scope),
                AuditDetail.FOREIGN: foreign,
            },
        )


@dataclass(frozen=True)
class RobotsTyped(SeparationCheck):
    """
    R4: every robot root carries the robot entity type, the mark that does not depend on
    Isaac Sim's schema.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        marks = RobotMarks()
        untyped = [
            str(root.GetPath())
            for root in twin.roots
            if not marks.has_entity_type(root)
        ]
        return AuditLine(
            check=AuditCheckName.ROBOTS_TYPED,
            passed=not untyped,
            what=f"every robot root has {ENTITY_TYPE_ATTRIBUTE} = "
            f'"{RobotMarker.ROBOT_ENTITY_TYPE}"',
            details={AuditDetail.MISSING: untyped},
        )


@dataclass(frozen=True)
class EnvironmentWithoutRobots(SeparationCheck):
    """
    R5: the environment layer, opened on its own, has no prim in the robots scope and no
    robot mark.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        environment = twin.layer_file(TwinLayer.ENVIRONMENT)
        if not environment.is_file():
            return AuditLine(
                check=AuditCheckName.ENVIRONMENT_WITHOUT_ROBOTS,
                passed=False,
                what="environment layer opened on its own",
                details={AuditDetail.MISSING: environment.name},
            )
        alone = Usd.Stage.Open(str(environment))
        marks = RobotMarks()
        leaked = [
            str(prim.GetPath())
            for prim in Usd.PrimRange(
                alone.GetPseudoRoot(), Usd.TraverseInstanceProxies()
            )
            if prim.GetPath().HasPrefix(twin.scope) or marks.mark_of(prim) is not None
        ]
        return AuditLine(
            check=AuditCheckName.ENVIRONMENT_WITHOUT_ROBOTS,
            passed=not leaked,
            what=f"{environment.name} alone holds no robot",
            details={AuditDetail.LEAKED: leaked},
        )


@dataclass(frozen=True)
class RobotsLayerConfined(SeparationCheck):
    """
    R6: the robots layer authors prims only in the robots scope and on the prims above
    it.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        robots = twin.layer_file(TwinLayer.ROBOTS)
        if not robots.is_file():
            return AuditLine(
                check=AuditCheckName.ROBOTS_LAYER_CONFINED,
                passed=False,
                what="robots layer",
                details={AuditDetail.MISSING: robots.name},
            )
        specs: List[Sdf.Path] = []
        Sdf.Layer.FindOrOpen(str(robots)).Traverse(
            Sdf.Path.absoluteRootPath, specs.append
        )
        prims = {
            path.StripAllVariantSelections()
            for path in specs
            if path.IsPrimPath() or path.IsPrimVariantSelectionPath()
        }
        stray = sorted(
            str(path)
            for path in prims
            if not path.HasPrefix(twin.scope) and not twin.scope.HasPrefix(path)
        )
        return AuditLine(
            check=AuditCheckName.ROBOTS_LAYER_CONFINED,
            passed=not stray,
            what=f"{robots.name} authors prims only in {twin.scope} (and an over on "
            "its parents)",
            details={AuditDetail.STRAY: stray},
        )


@dataclass(frozen=True)
class NoJointToRobots(SeparationCheck):
    """
    R7: no joint outside the robots scope and the robot roots connects to a robot body;
    mount and grasp joints live in the robot's subtree, so the environment stands alone.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        crossing = []
        for prim in Usd.PrimRange(
            twin.stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()
        ):
            if not prim.IsA(UsdPhysics.Joint) or twin.in_robots(prim.GetPath()):
                continue
            joint = UsdPhysics.Joint(prim)
            bodies = joint.GetBody0Rel().GetTargets() + joint.GetBody1Rel().GetTargets()
            if any(twin.in_robots(body) for body in bodies):
                crossing.append(str(prim.GetPath()))
        return AuditLine(
            check=AuditCheckName.NO_JOINT_TO_ROBOTS,
            passed=not crossing,
            what=f"no joint outside {twin.scope} connects to a robot body",
            details={AuditDetail.CROSSING: crossing},
        )


@dataclass(frozen=True)
class RobotsHaveGeometry(SeparationCheck):
    """
    R8: every robot root has geometry, a sign its reference resolved.
    """

    def evaluate(self, twin: AuditedTwin) -> AuditLine:
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
        empty = [
            str(root.GetPath())
            for root in twin.roots
            if cache.ComputeWorldBound(root).ComputeAlignedRange().IsEmpty()
        ]
        return AuditLine(
            check=AuditCheckName.ROBOTS_HAVE_GEOMETRY,
            passed=not empty,
            what="every robot root has geometry",
            details={AuditDetail.EMPTY: empty},
        )


# %% audit


@dataclass(frozen=True)
class SeparationAudit:
    """
    The checks the audit runs on a twin.
    """

    checks: List[SeparationCheck]
    """
    The checks, in the order they run.
    """

    @classmethod
    def of_twin(cls, without_robots: bool) -> SeparationAudit:
        """
        :param without_robots: Whether the twin is declared to have no robots.
        :return: Every check; the layer checks are moot for a twin without robots.
        """
        layers: List[SeparationCheck] = (
            []
            if without_robots
            else [EnvironmentWithoutRobots(), RobotsLayerConfined()]
        )
        composed: List[SeparationCheck] = [] if without_robots else [LayersComposed()]
        return cls(
            [
                MarkedRobots(),
                *composed,
                RobotsInScope(),
                ScopeHoldsRobotsOnly(),
                RobotsTyped(),
                *layers,
                NoJointToRobots(),
                RobotsHaveGeometry(),
            ]
        )

    def run(self, twin: AuditedTwin) -> List[AuditLine]:
        """
        :param twin: The audited twin.
        :return: The outcome of every check.
        """
        return [check.evaluate(twin) for check in self.checks]
