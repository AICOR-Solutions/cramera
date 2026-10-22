"""
The gate a staged export passes before it is published.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from typing_extensions import List, Optional, Self

from cramera_protocol.bundle.conversion_report import ConversionReport
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.index import SceneIndex, SceneIndexEntry
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.bundle.semantics import Semantics
from cramera_usd.bundle.index import NO_ROBOT, ScenesIndex
from cramera_usd.bundle.json_file import JsonFile
from cramera_usd.names import PrimPath

# %% constants

EXAMPLE_LIMIT = 5
"""
How many offending paths a check names.
"""

# %% staged bundle


@dataclass(frozen=True)
class StagedBundle:
    """
    The documents of a bundle converted into a staging directory.
    """

    name: str
    """
    The bundle's name.
    """

    scene: SceneDescription
    """
    Its ``scene.json``.
    """

    report: ConversionReport
    """
    Its ``conversion_report.json``.
    """

    semantics: Semantics
    """
    Its ``semantics.json``.
    """

    index: Optional[SceneIndex]
    """
    The staging directory's ``index.json``, or None when the conversion wrote none.
    """

    @classmethod
    def read(cls, staging: Path, name: str) -> Self:
        """
        :param staging: The staging directory.
        :param name: The bundle's name.
        :return: The staged bundle's documents.
        """
        bundle = staging / name
        return cls(
            name=name,
            scene=SceneDescription.from_json(
                JsonFile(bundle / BundleFile.SCENE).read()
            ),
            report=ConversionReport.from_json(
                JsonFile(bundle / BundleFile.CONVERSION_REPORT).read()
            ),
            semantics=Semantics.from_json(
                JsonFile(bundle / BundleFile.SEMANTICS).read()
            ),
            index=ScenesIndex(staging).read(),
        )

    @property
    def entry(self) -> Optional[SceneIndexEntry]:
        """
        The bundle's entry in the index, or None when the index does not list it.
        """
        if self.index is None:
            return None
        return self.index.entry(self.name)

    @property
    def left_out(self) -> List[str]:
        """
        The USD paths of the prims left out with their subtrees.
        """
        return [item.path for item in self.report.excluded]


# %% outcomes


class CheckVerdict(StrEnum):
    """
    How a check's outcome is printed.
    """

    PASS = "PASS"
    """
    The check passed.
    """

    FAIL = "FAIL"
    """
    The check failed.
    """


@dataclass(frozen=True)
class CheckOutcome:
    """
    The result of one check of the gate.
    """

    passed: bool
    """
    Whether the check passed.
    """

    description: str
    """
    What the check demands, with what it found.
    """

    def line(self) -> str:
        """
        :return: The outcome as one line: the verdict, then the description.
        """
        verdict = CheckVerdict.PASS if self.passed else CheckVerdict.FAIL
        return f"{verdict} {self.description}"


class GateCheck(ABC):
    """
    One demand a staged bundle meets before it is published.
    """

    @abstractmethod
    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        """
        :param bundle: The staged bundle.
        :return: Whether the bundle meets the demand.
        """

    @staticmethod
    def found(items: List[str]) -> str:
        """
        :param items: What a check found wrong.
        :return: A few of them for the check's description, or nothing.
        """
        return f" {items[:EXAMPLE_LIMIT]}" if items else ""


# %% checks of every bundle


@dataclass(frozen=True)
class MaterialsMapped(GateCheck):
    """
    Every authored shader input was carried over.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        unmapped = [
            f"{material}: {inputs}"
            for material, inputs in bundle.report.unmapped_inputs.items()
        ]
        return CheckOutcome(
            not unmapped, f"no unmapped material inputs{self.found(unmapped)}"
        )


@dataclass(frozen=True)
class TexturesFound(GateCheck):
    """
    Every texture resolved to a file.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        missing = bundle.report.missing_textures
        return CheckOutcome(not missing, f"no missing textures{self.found(missing)}")


@dataclass(frozen=True)
class IndexedWithEnvironment(GateCheck):
    """
    The index lists the bundle with the environment name its robot variants pair with.
    """

    environment: str
    """
    The environment name the export gave.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        entry = bundle.entry
        return CheckOutcome(
            entry is not None and entry.environment == self.environment,
            f"index.json lists {bundle.name} with environment {self.environment!r}: "
            f"{None if entry is None else json.dumps(entry.to_json())}",
        )


# %% checks of an environment


@dataclass(frozen=True)
class EnvironmentOnly(GateCheck):
    """
    The bundle holds no robot model.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        robots = [model.name for model in bundle.scene.models if model.robot]
        return CheckOutcome(
            not robots and bundle.scene.robot is None,
            f"environment only: no robot model{self.found(robots)}",
        )


@dataclass(frozen=True)
class RobotsLeftOut(GateCheck):
    """
    The conversion left the stage's robots out.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        return CheckOutcome(
            bool(bundle.left_out),
            "the stage's robots were left out (conversion_report.json 'excluded' is "
            "not empty; exclude a robot the stage does not mark, or declare a twin "
            "without robots)",
        )


@dataclass(frozen=True)
class NothingLeftOut(GateCheck):
    """
    A twin declared without robots had nothing to leave out.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        return CheckOutcome(
            not bundle.left_out,
            "the twin declares no robots and nothing was left out"
            f"{self.found(bundle.left_out)}",
        )


@dataclass(frozen=True)
class ExclusionsReported(GateCheck):
    """
    Every prim the export asked to leave out is reported as left out.
    """

    requested: List[str] = field(default_factory=list)
    """
    The prims the export asked to leave out.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        missing = [path for path in self.requested if path not in bundle.left_out]
        return CheckOutcome(
            not missing, f"every excluded prim is reported{self.found(missing)}"
        )


@dataclass(frozen=True)
class NoMovingDetachedBody(GateCheck):
    """
    No body that hung from a left-out body still moves parts: such a body is a robot
    part beside the marked robot.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        parts = [item.body for item in bundle.report.detached if item.movable_joints]
        return CheckOutcome(
            not parts,
            "no detached body still moves parts (a robot part beside the marked "
            f"robot: exclude it){self.found(parts)}",
        )


@dataclass(frozen=True)
class NoSemanticsLeftOut(GateCheck):
    """
    No prim with semantics lies below a prim the conversion left out.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        inside = [
            path
            for path in bundle.semantics.prims
            if any(PrimPath(left_out).holds(path) for left_out in bundle.left_out)
        ]
        return CheckOutcome(
            not inside, f"no semantic prim below a left-out prim{self.found(inside)}"
        )


@dataclass(frozen=True)
class BenchOnly(GateCheck):
    """
    The index lists the bundle without a robot, which the picker shows as the bench
    alone.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        entry = bundle.entry
        return CheckOutcome(
            entry is not None and entry.robot == NO_ROBOT,
            "it shows without a robot in the viewer's robot picker",
        )


# %% checks of a replay


@dataclass(frozen=True)
class ReplayNamesRobot(GateCheck):
    """
    The index lists a replay with the robot it replays.
    """

    def evaluate(self, bundle: StagedBundle) -> CheckOutcome:
        entry = bundle.entry
        robot = None if entry is None else entry.robot
        return CheckOutcome(
            entry is not None and entry.robot != NO_ROBOT,
            f"the replay names its robot ({robot!r})",
        )


# %% gate


@dataclass(frozen=True)
class ExportGate:
    """
    The checks an export of one kind runs.
    """

    checks: List[GateCheck]
    """
    The checks, in the order they run.
    """

    @classmethod
    def of_export(
        cls,
        environment: str,
        replay: bool,
        without_robots: bool,
        requested: List[str],
    ) -> Self:
        """
        :param environment: The environment name the export gave.
        :param replay: Whether the export is a replay of a recorded run.
        :param without_robots: Whether the twin is declared to have no robots.
        :param requested: The prims the export asked to leave out.
        :return: The gate of that export: a replay keeps its robot, an environment
            export proves the robots are out.
        """
        checks: List[GateCheck] = [MaterialsMapped(), TexturesFound()]
        if not replay:
            checks += [
                EnvironmentOnly(),
                NothingLeftOut() if without_robots else RobotsLeftOut(),
                ExclusionsReported(requested),
                NoMovingDetachedBody(),
                NoSemanticsLeftOut(),
            ]
        checks.append(IndexedWithEnvironment(environment))
        checks.append(ReplayNamesRobot() if replay else BenchOnly())
        return cls(checks)

    def evaluate(self, bundle: StagedBundle) -> List[CheckOutcome]:
        """
        :param bundle: The staged bundle.
        :return: The outcome of every check.
        """
        return [check.evaluate(bundle) for check in self.checks]
