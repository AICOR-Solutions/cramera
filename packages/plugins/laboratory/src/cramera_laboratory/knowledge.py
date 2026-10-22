"""
The centrifuge's operating knowledge: manuals in a small Markdown format, the one rule
they state, the revisions the laboratory accepted, and the start requirements checked
against what the simulation measures.

A manual states its rule in a table of its ``Operating rules`` section::

    | Rule | Value |
    | --- | --- |
    | Minimum secured samples | 2 |
"""

from __future__ import annotations

import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

from typing_extensions import List, Tuple

from cramera_laboratory.exceptions import InvalidManual, ManualProblem
from cramera_laboratory.resources import RESOURCES_DIRECTORY, LaboratoryResource
from cramera_protocol.laboratory.knowledge import (
    ManualCitation,
    ManualEdition,
    ManualRevision,
    ManualSummary,
    OperatingKnowledge,
    OperatingRule,
    RuleChange,
    StartEvaluation,
    StartRequirement,
    StartRequirementName,
)

MAXIMUM_MANUAL_BYTES = 8192
"""
The largest manual read, in bytes of UTF-8.
"""

ALLOWED_MINIMUMS = (2, 4)
"""
The sample counts a manual may ask for: one or both opposite pairs of the four holders.
"""

HISTORY_LIMIT = 20
"""
How many accepted revisions the knowledge keeps.
"""

VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
"""
What a manual's version may look like.
"""

SEPARATOR_CELL = re.compile(r":?-{3,}:?")
"""
A cell of a Markdown table's separator row.
"""

SURROGATES = re.compile(r"[\ud800-\udfff]")
"""
Code points that cannot be encoded on their own.
"""

MANUAL_SUFFIX = ".md"
"""
The suffix of a shipped manual's file.
"""

# %% syntax


class ManualSyntax(StrEnum):
    """
    The parts of a manual the reader recognises.
    """

    TITLE_PREFIX = "# "
    """
    What starts the title line.
    """

    SECTION_PREFIX = "## "
    """
    What starts a section heading.
    """

    HEADING_MARK = "#"
    """
    What starts any heading, which ends the rule section.
    """

    VERSION_PREFIX = "Document version:"
    """
    What starts the version line.
    """

    RULE_SECTION = "Operating rules"
    """
    The heading of the section stating the rule.
    """

    MINIMUM_SAMPLES = "Minimum secured samples"
    """
    The rule's name in the table.
    """

    RULE_HEADER = "Rule"
    """
    The table's first column heading.
    """

    VALUE_HEADER = "Value"
    """
    The table's second column heading.
    """

    CELL_SEPARATOR = "|"
    """
    What separates table cells.
    """

    VERSION_SEPARATOR = ":"
    """
    What separates the version line's label from the version.
    """


class GermanManualSyntax(StrEnum):
    """
    The German wording earlier manuals used for the same parts.
    """

    VERSION_PREFIX = "Dokumentversion:"
    """
    What starts the version line.
    """

    RULE_SECTION = "Betriebsregeln"
    """
    The heading of the section stating the rule.
    """

    MINIMUM_SAMPLES = "Mindestzahl gesicherter Proben"
    """
    The rule's name in the table.
    """

    RULE_HEADER = "Regel"
    """
    The table's first column heading.
    """

    VALUE_HEADER = "Wert"
    """
    The table's second column heading.
    """


TABLE_COLUMNS = 2
"""
How many columns the rule table has.
"""

# %% manual


@dataclass(frozen=True)
class CentrifugeManual:
    """
    A manual that was read, with the rule it states.
    """

    title: str
    """
    The manual's title.
    """

    version: str
    """
    The version the manual states.
    """

    document: str
    """
    The manual's text, exactly as given.
    """

    minimum_samples: int
    """
    How many samples must be secured before a run.
    """

    citation: ManualCitation
    """
    Where the manual states the rule.
    """

    @classmethod
    def shipped(cls, edition: ManualEdition) -> CentrifugeManual:
        """
        :param edition: A shipped edition.
        :return: The edition, read.
        """
        path = (
            RESOURCES_DIRECTORY
            / LaboratoryResource.MANUALS
            / f"{edition.value}{MANUAL_SUFFIX}"
        )
        return cls.of_text(path.read_text(encoding="utf-8"))

    @classmethod
    def of_text(cls, document: str) -> CentrifugeManual:
        """
        :param document: A manual's Markdown text.
        :return: The manual, read.
        :raises InvalidManual: When the text is not a manual stating one supported
            rule.
        """
        if (
            not document
            or SURROGATES.search(document)
            or len(document.encode("utf-8")) > MAXIMUM_MANUAL_BYTES
        ):
            raise InvalidManual(ManualProblem.TOO_LONG)
        lines = document.splitlines()
        titles = [
            line.removeprefix(ManualSyntax.TITLE_PREFIX).strip()
            for line in lines
            if line.startswith(ManualSyntax.TITLE_PREFIX)
        ]
        if len(titles) != 1 or not titles[0]:
            raise InvalidManual(ManualProblem.TITLE)
        versions = [
            line.split(ManualSyntax.VERSION_SEPARATOR, 1)[1].strip()
            for line in lines
            if line.startswith(
                (ManualSyntax.VERSION_PREFIX, GermanManualSyntax.VERSION_PREFIX)
            )
        ]
        if len(versions) != 1 or VERSION_PATTERN.fullmatch(versions[0]) is None:
            raise InvalidManual(ManualProblem.VERSION)
        section = RuleSection.of_lines(lines)
        line_index, value = section.rule()
        return cls(
            title=titles[0],
            version=versions[0],
            document=document,
            minimum_samples=value,
            citation=ManualCitation(
                section=section.heading,
                line=line_index + 1,
                quote=lines[line_index],
            ),
        )

    @property
    def digest(self) -> str:
        """
        The hexadecimal SHA-256 digest of the text in UTF-8.
        """
        return hashlib.sha256(self.document.encode("utf-8")).hexdigest()

    def summary(self) -> ManualSummary:
        """
        :return: The manual as the browser reads it.
        """
        return ManualSummary(
            title=self.title,
            version=self.version,
            document=self.document,
            digest=self.digest,
            minimum_samples=self.minimum_samples,
            citation=self.citation,
        )


@dataclass(frozen=True)
class RuleSection:
    """
    The ``Operating rules`` section of a manual.
    """

    lines: List[str]
    """
    Every line of the manual.
    """

    start: int
    """
    The index of the section's heading line.
    """

    @classmethod
    def of_lines(cls, lines: List[str]) -> RuleSection:
        """
        :param lines: Every line of a manual.
        :return: Its rule section.
        :raises InvalidManual: When the manual has no or several rule sections.
        """
        headings = {
            f"{ManualSyntax.SECTION_PREFIX}{ManualSyntax.RULE_SECTION}",
            f"{ManualSyntax.SECTION_PREFIX}{GermanManualSyntax.RULE_SECTION}",
        }
        starts = [index for index, line in enumerate(lines) if line.strip() in headings]
        if len(starts) != 1:
            raise InvalidManual(ManualProblem.RULE_SECTION)
        return cls(lines=lines, start=starts[0])

    @property
    def heading(self) -> str:
        """
        The section's heading, without its mark.
        """
        return self.lines[self.start].strip().removeprefix(ManualSyntax.SECTION_PREFIX)

    def rule(self) -> Tuple[int, int]:
        """
        :return: The index of the line stating the minimum sample count, and the count.
        :raises InvalidManual: When the table is malformed or does not state exactly
            one supported rule.
        """
        headers = (
            [ManualSyntax.RULE_HEADER, ManualSyntax.VALUE_HEADER],
            [GermanManualSyntax.RULE_HEADER, GermanManualSyntax.VALUE_HEADER],
        )
        names = (ManualSyntax.MINIMUM_SAMPLES, GermanManualSyntax.MINIMUM_SAMPLES)
        allowed = [str(count) for count in ALLOWED_MINIMUMS]
        header_seen = separator_seen = False
        rows: List[Tuple[int, int]] = []
        for index in range(self.start + 1, len(self.lines)):
            line = self.lines[index]
            if line.lstrip().startswith(ManualSyntax.HEADING_MARK):
                break
            if not line.strip():
                continue
            cells = [
                cell.strip()
                for cell in line.strip()
                .strip(ManualSyntax.CELL_SEPARATOR)
                .split(ManualSyntax.CELL_SEPARATOR)
            ]
            if cells in headers:
                if header_seen or separator_seen or rows:
                    raise InvalidManual(ManualProblem.HEADER)
                header_seen = True
                continue
            if len(cells) == TABLE_COLUMNS and all(
                SEPARATOR_CELL.fullmatch(cell) for cell in cells
            ):
                if not header_seen or separator_seen or rows:
                    raise InvalidManual(ManualProblem.SEPARATOR)
                separator_seen = True
                continue
            if (
                not separator_seen
                or len(cells) != TABLE_COLUMNS
                or cells[0] not in names
                or cells[1] not in allowed
            ):
                raise InvalidManual(ManualProblem.UNSUPPORTED_RULE)
            rows.append((index, int(cells[1])))
        if len(rows) != 1:
            raise InvalidManual(ManualProblem.RULE_COUNT)
        return rows[0]


# %% observations


@dataclass(frozen=True)
class CentrifugeObservation:
    """
    What the simulation measures of the centrifuge, as far as starting depends on it.
    """

    secured_samples: int
    """
    How many holders clamp a vessel.
    """

    balanced: bool
    """
    Whether every clamped vessel has an opposite vessel of equal mass.
    """

    lid_closed: bool
    """
    Whether the lid is closed.
    """

    stopped: bool
    """
    Whether the rotor stands still and is not driven.
    """


class NextStep(StrEnum):
    """
    What a person does next to start the centrifuge.
    """

    START = "Start the centrifuge cycle."
    """
    Everything holds.
    """

    STOP = "Stop the rotor and wait for it to come to rest."
    """
    The rotor turns.
    """

    LOAD = "Load and secure {missing} more samples in opposite holders."
    """
    Too few samples are secured; formatted with the number missing.
    """

    OPEN_FOR_LOADING = "Open the lid first; close it again after securing the samples."
    """
    Samples are missing while the lid is closed.
    """

    BALANCE = "Check and balance the mass of opposite samples."
    """
    The load is unbalanced.
    """

    CLOSE = "Close the lid completely."
    """
    The lid is open.
    """


# %% knowledge


@dataclass
class ManualKnowledge:
    """
    The manual the centrifuge follows and the revisions the laboratory accepted.

    It
    survives a reset of the simulation: what was read stays read.
    """

    active: CentrifugeManual = field(
        default_factory=lambda: CentrifugeManual.shipped(ManualEdition.FIRST)
    )
    """
    The manual followed.
    """

    revision: int = field(init=False, default=1)
    """
    The number of the current revision.
    """

    history: deque = field(init=False)
    """
    The accepted :class:`ManualRevision` documents, the latest last.
    """

    def __post_init__(self) -> None:
        self.history = deque(maxlen=HISTORY_LIMIT)
        self.history.append(
            ManualRevision(
                revision=self.revision,
                version=self.active.version,
                digest=self.active.digest,
            )
        )

    def read(self, manual: CentrifugeManual, simulation_time: float) -> None:
        """
        Follow another manual; the same text again changes nothing.

        :param manual: The manual.
        :param simulation_time: When it is read, in simulated seconds.
        """
        if manual.digest == self.active.digest:
            return
        changes = []
        if manual.minimum_samples != self.active.minimum_samples:
            changes.append(
                RuleChange(
                    rule=OperatingRule.MINIMUM_SAMPLES,
                    before=self.active.minimum_samples,
                    after=manual.minimum_samples,
                    citation=manual.citation,
                )
            )
        self.active = manual
        self.revision += 1
        self.history.append(
            ManualRevision(
                revision=self.revision,
                version=manual.version,
                digest=manual.digest,
                changes=changes,
                simulation_time=simulation_time,
            )
        )

    def evaluate(self, observation: CentrifugeObservation) -> StartEvaluation:
        """
        :param observation: What the simulation measures.
        :return: Each start requirement against the measurements, and what to do next.
        """
        requirements = [
            StartRequirement(
                name=StartRequirementName.AVAILABLE,
                satisfied=True,
                actual=True,
                required=True,
            ),
            StartRequirement(
                name=StartRequirementName.MINIMUM_SAMPLES,
                satisfied=observation.secured_samples >= self.active.minimum_samples,
                actual=observation.secured_samples,
                required=self.active.minimum_samples,
                citation=self.active.citation,
            ),
            StartRequirement(
                name=StartRequirementName.BALANCED,
                satisfied=observation.balanced,
                actual=observation.balanced,
                required=True,
            ),
            StartRequirement(
                name=StartRequirementName.LID_CLOSED,
                satisfied=observation.lid_closed,
                actual=observation.lid_closed,
                required=True,
            ),
            StartRequirement(
                name=StartRequirementName.STOPPED,
                satisfied=observation.stopped,
                actual=observation.stopped,
                required=True,
            ),
        ]
        allowed = all(requirement.satisfied for requirement in requirements)
        return StartEvaluation(
            allowed=allowed,
            requirements=requirements,
            next_steps=self.next_steps(observation, allowed),
        )

    def next_steps(
        self, observation: CentrifugeObservation, allowed: bool
    ) -> List[str]:
        """
        :param observation: What the simulation measures.
        :param allowed: Whether every requirement holds.
        :return: What a person does next, in order.
        """
        if allowed:
            return [NextStep.START.value]
        steps: List[str] = []
        if not observation.stopped:
            steps.append(NextStep.STOP.value)
        missing = self.active.minimum_samples - observation.secured_samples
        if missing > 0:
            steps.append(NextStep.LOAD.value.format(missing=missing))
            if observation.lid_closed:
                steps.append(NextStep.OPEN_FOR_LOADING.value)
        if not observation.balanced:
            steps.append(NextStep.BALANCE.value)
        if not observation.lid_closed:
            steps.append(NextStep.CLOSE.value)
        return steps

    def document(self, observation: CentrifugeObservation) -> OperatingKnowledge:
        """
        :param observation: What the simulation measures.
        :return: The knowledge as the browser reads it.
        """
        return OperatingKnowledge(
            manual=self.active.summary(),
            revision=self.revision,
            history=list(self.history),
            evaluation=self.evaluate(observation),
        )
