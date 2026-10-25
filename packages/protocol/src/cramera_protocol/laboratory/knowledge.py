"""
The centrifuge's operating knowledge: the manual a person gave the laboratory, the rule
it states, the revisions it went through and the start requirements evaluated against
the simulation's measurements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, List, Optional

from cramera_protocol.document import JsonDocument, document_field

# %% editions


class ManualEdition(StrEnum):
    """
    The manual editions the laboratory ships.
    """

    FIRST = "v1"
    """
    The edition that lets one balanced pair of samples run.
    """

    SECOND = "v2"
    """
    The edition that asks for two balanced pairs.
    """


# %% citations


class CitationKey(StrEnum):
    """
    The keys of a citation of a manual line.
    """

    SECTION = "section"
    """
    The section holding the line.
    """

    LINE = "line"
    """
    The line's number, counted from one.
    """

    QUOTE = "quote"
    """
    The line as the manual writes it.
    """


@dataclass(kw_only=True)
class ManualCitation(JsonDocument):
    """
    The manual line a rule was read from.
    """

    section: str = document_field(CitationKey.SECTION)
    """
    The heading of the section holding the line.
    """

    line: int = document_field(CitationKey.LINE)
    """
    The line's number in the manual, counted from one.
    """

    quote: str = document_field(CitationKey.QUOTE)
    """
    The line as the manual writes it.
    """


# %% manual


class ManualKey(StrEnum):
    """
    The keys of the manual the laboratory follows.
    """

    TITLE = "title"
    """
    The manual's title.
    """

    VERSION = "version"
    """
    The version the manual states.
    """

    DOCUMENT = "document"
    """
    The manual's Markdown text.
    """

    DIGEST = "digest"
    """
    The SHA-256 digest of the text.
    """

    MINIMUM_SAMPLES = "minimumSamples"
    """
    The rule the manual states: how many samples must be secured before a run.
    """

    CITATION = "citation"
    """
    Where the manual states the rule.
    """


@dataclass(kw_only=True)
class ManualSummary(JsonDocument):
    """
    The manual the laboratory follows, with the rule read from it.
    """

    title: str = document_field(ManualKey.TITLE)
    """
    The manual's title.
    """

    version: str = document_field(ManualKey.VERSION)
    """
    The version the manual states.
    """

    document: str = document_field(ManualKey.DOCUMENT)
    """
    The manual's Markdown text, exactly as it was read.
    """

    digest: str = document_field(ManualKey.DIGEST)
    """
    The hexadecimal SHA-256 digest of the text in UTF-8.
    """

    minimum_samples: int = document_field(ManualKey.MINIMUM_SAMPLES)
    """
    How many samples must be secured in the rotor before a run.
    """

    citation: ManualCitation = document_field(ManualKey.CITATION)
    """
    Where the manual states the rule.
    """


# %% revisions


class OperatingRule(StrEnum):
    """
    The rules a manual can state.
    """

    MINIMUM_SAMPLES = "minimumSamples"
    """
    How many samples must be secured before a run.
    """


class RuleChangeKey(StrEnum):
    """
    The keys of a rule a newly read manual changed.
    """

    RULE = "rule"
    """
    An :class:`OperatingRule` value.
    """

    BEFORE = "before"
    """
    The rule's value before.
    """

    AFTER = "after"
    """
    The rule's value after.
    """

    CITATION = "citation"
    """
    Where the new manual states the new value.
    """


@dataclass(kw_only=True)
class RuleChange(JsonDocument):
    """
    A rule a newly read manual changed.
    """

    rule: OperatingRule = document_field(RuleChangeKey.RULE)
    """
    The rule.
    """

    before: int = document_field(RuleChangeKey.BEFORE)
    """
    The rule's value before the manual was read.
    """

    after: int = document_field(RuleChangeKey.AFTER)
    """
    The rule's value the new manual states.
    """

    citation: ManualCitation = document_field(RuleChangeKey.CITATION)
    """
    Where the new manual states the new value.
    """


class RevisionKey(StrEnum):
    """
    The keys of one accepted manual revision.
    """

    REVISION = "revision"
    """
    The revision's number.
    """

    VERSION = "version"
    """
    The version the manual states.
    """

    DIGEST = "digest"
    """
    The manual text's digest.
    """

    CHANGES = "changes"
    """
    The rules the manual changed.
    """

    SIMULATION_TIME = "simulationTime"
    """
    When the manual was read, in simulated seconds.
    """


@dataclass(kw_only=True)
class ManualRevision(JsonDocument):
    """
    One manual the laboratory accepted.
    """

    revision: int = document_field(RevisionKey.REVISION)
    """
    The revision's number, counted from one.
    """

    version: str = document_field(RevisionKey.VERSION)
    """
    The version the manual states.
    """

    digest: str = document_field(RevisionKey.DIGEST)
    """
    The manual text's digest.
    """

    changes: List[RuleChange] = document_field(
        RevisionKey.CHANGES, default_factory=list
    )
    """
    The rules the manual changed against its predecessor.
    """

    simulation_time: Optional[float] = document_field(
        RevisionKey.SIMULATION_TIME, default=None
    )
    """
    When the manual was read, in simulated seconds; None for the manual the laboratory
    starts with.
    """


# %% start evaluation


class StartRequirementName(StrEnum):
    """
    What must hold before the centrifuge may start.
    """

    AVAILABLE = "available"
    """
    The laboratory has a centrifuge.
    """

    MINIMUM_SAMPLES = "minimumSamples"
    """
    At least as many samples are secured as the manual asks for.
    """

    BALANCED = "balanced"
    """
    Every secured sample has an opposite sample of the same mass.
    """

    LID_CLOSED = "lidClosed"
    """
    The lid is closed.
    """

    STOPPED = "stopped"
    """
    The rotor stands still.
    """


class RequirementKey(StrEnum):
    """
    The keys of one evaluated start requirement.
    """

    NAME = "name"
    """
    A :class:`StartRequirementName` value.
    """

    SATISFIED = "satisfied"
    """
    Whether it holds; absent when the measurements do not tell.
    """

    ACTUAL = "actual"
    """
    The measured value.
    """

    REQUIRED = "required"
    """
    The value that must be measured.
    """

    CITATION = "citation"
    """
    The manual line the requirement comes from.
    """


@dataclass(kw_only=True)
class StartRequirement(JsonDocument):
    """
    One requirement for starting the centrifuge, compared with what the simulation
    measures.
    """

    name: StartRequirementName = document_field(RequirementKey.NAME)
    """
    What must hold.
    """

    satisfied: Optional[bool] = document_field(RequirementKey.SATISFIED, default=None)
    """
    Whether it holds; None when the measurements do not tell.
    """

    actual: Any = document_field(RequirementKey.ACTUAL, default=None)
    """
    The measured value: a count for :attr:`StartRequirementName.MINIMUM_SAMPLES`, a
    truth value otherwise, None when unknown.
    """

    required: Any = document_field(RequirementKey.REQUIRED)
    """
    The value that must be measured, of the same kind as :attr:`actual`.
    """

    citation: Optional[ManualCitation] = document_field(
        RequirementKey.CITATION, default=None
    )
    """
    The manual line the requirement comes from; None for a requirement measured directly
    in the simulation.
    """


class EvaluationKey(StrEnum):
    """
    The keys of an evaluation of the start requirements.
    """

    ALLOWED = "allowed"
    """
    Whether every requirement holds.
    """

    REQUIREMENTS = "requirements"
    """
    The requirements.
    """

    NEXT_STEPS = "nextSteps"
    """
    What a person does next.
    """


@dataclass(kw_only=True)
class StartEvaluation(JsonDocument):
    """
    The centrifuge's start requirements, evaluated against the simulation.
    """

    allowed: bool = document_field(EvaluationKey.ALLOWED)
    """
    Whether every requirement is known to hold.
    """

    requirements: List[StartRequirement] = document_field(EvaluationKey.REQUIREMENTS)
    """
    The requirements.
    """

    next_steps: List[str] = document_field(EvaluationKey.NEXT_STEPS)
    """
    What a person does next, one sentence each.
    """


# %% knowledge


class KnowledgeKey(StrEnum):
    """
    The keys of the centrifuge's operating knowledge.
    """

    MANUAL = "manual"
    """
    The manual followed.
    """

    REVISION = "revision"
    """
    The number of the current revision.
    """

    HISTORY = "history"
    """
    The accepted revisions, the latest last.
    """

    EVALUATION = "evaluation"
    """
    The start requirements, evaluated now.
    """


@dataclass(kw_only=True)
class OperatingKnowledge(JsonDocument):
    """
    The manual the centrifuge is operated by, its history, and whether it may start.
    """

    manual: ManualSummary = document_field(KnowledgeKey.MANUAL)
    """
    The manual followed.
    """

    revision: int = document_field(KnowledgeKey.REVISION)
    """
    The number of the current revision.
    """

    history: List[ManualRevision] = document_field(KnowledgeKey.HISTORY)
    """
    The accepted revisions, the latest last; the oldest are dropped beyond a fixed
    number.
    """

    evaluation: StartEvaluation = document_field(KnowledgeKey.EVALUATION)
    """
    The start requirements, evaluated against the current measurements.
    """
