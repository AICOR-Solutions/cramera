"""
The robot separation audit's report, as its JSON file holds it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List

from cramera_protocol.document import JsonDocument, document_field, extension_field

# %% checks


class AuditCheckName(StrEnum):
    """
    The checks of the robot separation audit.
    """

    MARKED_ROBOTS = "R0"
    """
    The stage marks at least one robot root, or none for a twin without robots.
    """

    LAYERS_COMPOSED = "R1"
    """
    The root layer sublayers the twin's robots and environment layers.
    """

    ROBOTS_IN_SCOPE = "R2"
    """
    Every robot root is a direct child of the robots scope.
    """

    SCOPE_HOLDS_ROBOTS_ONLY = "R3"
    """
    Every child of the robots scope is a robot root.
    """

    ROBOTS_TYPED = "R4"
    """
    Every robot root carries the robot entity type.
    """

    ENVIRONMENT_WITHOUT_ROBOTS = "R5"
    """
    The environment layer on its own holds no robot.
    """

    ROBOTS_LAYER_CONFINED = "R6"
    """
    The robots layer authors prims only in the robots scope.
    """

    NO_JOINT_TO_ROBOTS = "R7"
    """
    No joint outside the robots connects to a robot body.
    """

    ROBOTS_HAVE_GEOMETRY = "R8"
    """
    Every robot root has geometry.
    """


class AuditDetail(StrEnum):
    """
    The keys of what a check found, written beside its outcome.
    """

    COUNT = "count"
    """
    The number of robot roots.
    """

    ROOTS = "roots"
    """
    The robot roots found.
    """

    MISSING = "missing"
    """
    What a check missed.
    """

    SUBLAYERS = "sublayers"
    """
    The root layer's sublayers.
    """

    OUTSIDE = "outside"
    """
    The robot roots outside the robots scope.
    """

    SCOPE_EXISTS = "scope_exists"
    """
    Whether the robots scope exists.
    """

    FOREIGN = "foreign"
    """
    The children of the robots scope that are no robot roots.
    """

    LEAKED = "leaked"
    """
    The robot prims in the environment layer.
    """

    STRAY = "stray"
    """
    The prims the robots layer authors outside the robots scope.
    """

    CROSSING = "crossing"
    """
    The joints that connect the environment to a robot body.
    """

    EMPTY = "empty"
    """
    The robot roots without geometry.
    """


# %% lines


class AuditLineKey(StrEnum):
    """
    The keys of one check's outcome.
    """

    CHECK = "check"
    """
    The check.
    """

    PASSED = "passed"
    """
    Whether it passed.
    """

    WHAT = "what"
    """
    What it demands.
    """


@dataclass(kw_only=True)
class AuditLine(JsonDocument):
    """
    The outcome of one check, with what it found.
    """

    check: AuditCheckName = document_field(AuditLineKey.CHECK)
    """
    The check.
    """

    passed: bool = document_field(AuditLineKey.PASSED)
    """
    Whether it passed.
    """

    what: str = document_field(AuditLineKey.WHAT)
    """
    What the check demands.
    """

    details: Dict[str, Any] = extension_field()
    """
    What the check found, by :class:`AuditDetail` key.
    """


# %% report


class AuditReportKey(StrEnum):
    """
    The keys of the audit's report.
    """

    GENERATED = "generated"
    """
    When the audit ran.
    """

    STAGE = "stage"
    """
    The audited stage.
    """

    ROBOTS = "robots"
    """
    The robot roots found.
    """

    PASSED = "passed"
    """
    How many checks passed.
    """

    TOTAL = "total"
    """
    How many checks ran.
    """

    LINES = "lines"
    """
    The outcome of every check.
    """


@dataclass(kw_only=True)
class AuditReport(JsonDocument):
    """
    The report of one robot separation audit.
    """

    generated: str = document_field(AuditReportKey.GENERATED)
    """
    When the audit ran, as an ISO 8601 date and time.
    """

    stage: str = document_field(AuditReportKey.STAGE)
    """
    The path of the audited stage.
    """

    robots: List[str] = document_field(AuditReportKey.ROBOTS, default_factory=list)
    """
    The paths of the robot roots found.
    """

    passed: int = document_field(AuditReportKey.PASSED)
    """
    How many checks passed.
    """

    total: int = document_field(AuditReportKey.TOTAL)
    """
    How many checks ran.
    """

    lines: List[AuditLine] = document_field(AuditReportKey.LINES, default_factory=list)
    """
    The outcome of every check, in the order they ran.
    """
