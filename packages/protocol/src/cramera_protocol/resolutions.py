"""
How a running plan's open parts were resolved before the robot carried it out: each open
part asked as a statement, the backend that answered it, its answers and how the backend
reasoned to them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional, Self

from cramera_protocol.document import JsonDocument, ValueLocation, document_field
from cramera_protocol.geometry import NumberArray, Pose, Vector3

# %% what the scene shows of an answer


class RegionOutlineKey(StrEnum):
    """
    The keys of a region drawn as a box.
    """

    IDENTIFIER = "id"
    """
    The region's name.
    """

    POSE = "pose"
    """
    The box's centre and orientation in the world.
    """

    SIZE = "size"
    """
    The box's extent along its own axes.
    """


@dataclass(kw_only=True)
class RegionOutline(JsonDocument):
    """
    A region of the world drawn as a box; a region has no geometry the scene shows.
    """

    identifier: str = document_field(RegionOutlineKey.IDENTIFIER)
    """
    The region's name.
    """

    pose: Pose = document_field(RegionOutlineKey.POSE)
    """
    The box's centre and orientation in the world.
    """

    size: Vector3 = document_field(RegionOutlineKey.SIZE)
    """
    The box's extent along its own x, y and z axes, in metres.
    """


class SceneHighlightKey(StrEnum):
    """
    The keys of what the scene lights up and frames.
    """

    KEYS = "keys"
    """
    The links and free objects lit up.
    """

    REGIONS = "regions"
    """
    The regions drawn as boxes.
    """

    FRAMED = "framed"
    """
    The links and free objects the camera moves onto.
    """


@dataclass(kw_only=True)
class SceneHighlight(JsonDocument):
    """
    What the scene lights up, outlines and frames while an answer is shown.
    """

    keys: List[str] = document_field(SceneHighlightKey.KEYS, default_factory=list)
    """
    The keys of the links and free objects lit up.
    """

    regions: List[RegionOutline] = document_field(
        SceneHighlightKey.REGIONS, default_factory=list
    )
    """
    The regions drawn as boxes.
    """

    framed: List[str] = document_field(SceneHighlightKey.FRAMED, default_factory=list)
    """
    The keys of the links and free objects the camera moves onto; none leaves the camera
    where it is.
    """


# %% knowledge sources


class KnowledgeSource(StrEnum):
    """
    The kind of knowledge a backend answers a statement from.
    """

    PERCEPTION = "perception"
    """
    What the robot's sensors saw.
    """

    WORKING_MEMORY = "working memory"
    """
    The robot's digital twin of the world.
    """

    RULES = "rules"
    """
    Rules stated about the task.
    """

    PROBABILISTIC = "probabilistic"
    """
    A probabilistic model the answers are sampled from.
    """


# %% reasoning


class ReasoningKey(StrEnum):
    """
    The key every kind of reasoning shares.
    """

    SOURCE = "source"
    """
    The kind of knowledge the reasoning drew on, which says what the rest holds.
    """


class Reasoning(JsonDocument, ABC):
    """
    How a backend reasoned to its answers; each kind of knowledge reasons in a way of
    its own.
    """

    @classmethod
    @abstractmethod
    def source(cls) -> KnowledgeSource:
        """
        :return: The kind of knowledge this reasoning draws on.
        """

    @classmethod
    def read_at(cls, data: Any, location: ValueLocation) -> Self:
        """
        Read the reasoning of the kind its :attr:`ReasoningKey.SOURCE` names; see
        :meth:`JsonDocument.read_at`.
        """
        if cls is not Reasoning:
            return super().read_at(data, location)
        if not isinstance(data, dict):
            raise location.invalid(data, "an object")
        named = data.get(ReasoningKey.SOURCE)
        kinds = {kind.source().value: kind for kind in cls.__subclasses__()}
        if named not in kinds:
            raise location.child(ReasoningKey.SOURCE).invalid(
                named, "one of " + ", ".join(sorted(kinds))
            )
        content = {
            key: value for key, value in data.items() if key != ReasoningKey.SOURCE
        }
        return kinds[named].read_at(content, location)

    def to_json(self) -> Dict[str, Any]:
        return {ReasoningKey.SOURCE.value: self.source().value, **super().to_json()}


class ReasoningImageKey(StrEnum):
    """
    The keys of an image a perception backend looked at.
    """

    IMAGE = "image"
    """
    The image's address.
    """

    CAPTION = "caption"
    """
    What the image shows.
    """


@dataclass(kw_only=True)
class ReasoningImage(JsonDocument):
    """
    An image a perception backend looked at.
    """

    image: str = document_field(ReasoningImageKey.IMAGE)
    """
    The image's address, a data URL where it is not served.
    """

    caption: str = document_field(ReasoningImageKey.CAPTION)
    """
    What the image shows.
    """


class OutlineFitKey(StrEnum):
    """
    The keys of how well something seen fits the kind asked about.
    """

    NAME = "name"
    """
    What was seen.
    """

    KIND = "kind"
    """
    The kind it was seen as.
    """

    FIT = "fit"
    """
    How well its outline fits the kind.
    """

    SELECTED = "selected"
    """
    Whether it answers the statement.
    """


@dataclass(kw_only=True)
class OutlineFit(JsonDocument):
    """
    How well the outline of something seen fits the kind a statement asks about.
    """

    name: str = document_field(OutlineFitKey.NAME)
    """
    The name of what was seen.
    """

    kind: str = document_field(OutlineFitKey.KIND)
    """
    The kind it was seen as.
    """

    fit: float = document_field(OutlineFitKey.FIT)
    """
    How well its outline agrees with the kind's, from 0 to 1.
    """

    selected: bool = document_field(OutlineFitKey.SELECTED)
    """
    Whether it answers the statement.
    """


class PerceptionReasoningKey(StrEnum):
    """
    The keys of a perception backend's reasoning.
    """

    IMAGES = "images"
    """
    The images looked at.
    """

    CANDIDATES = "candidates"
    """
    Everything seen with how well it fits.
    """


@dataclass(kw_only=True)
class PerceptionReasoning(Reasoning):
    """
    What a perception backend saw and how well each thing seen fits the statement.
    """

    images: List[ReasoningImage] = document_field(
        PerceptionReasoningKey.IMAGES, default_factory=list
    )
    """
    The images the backend looked at, in the order it looked at them.
    """

    candidates: List[OutlineFit] = document_field(
        PerceptionReasoningKey.CANDIDATES, default_factory=list
    )
    """
    Everything seen, with how well its outline fits.
    """

    @classmethod
    def source(cls) -> KnowledgeSource:
        return KnowledgeSource.PERCEPTION


class ContactReadingKey(StrEnum):
    """
    The keys of one contact a working-memory backend tested.
    """

    NAME = "name"
    """
    The thing tested.
    """

    SELECTED = "selected"
    """
    Whether it answers the statement.
    """

    RELATION = "relation"
    """
    The relation tested, in words.
    """

    SUPPORT = "support"
    """
    What it rests on.
    """

    GAP = "gap"
    """
    The gap between it and its support.
    """

    SIZE = "size"
    """
    The size of its collision box.
    """


@dataclass(kw_only=True)
class ContactReading(JsonDocument):
    """
    One thing a working-memory backend tested against the statement's condition.
    """

    name: str = document_field(ContactReadingKey.NAME)
    """
    The name of the thing tested.
    """

    selected: bool = document_field(ContactReadingKey.SELECTED)
    """
    Whether it answers the statement.
    """

    relation: str = document_field(ContactReadingKey.RELATION)
    """
    The relation tested, in words.
    """

    support: Optional[str] = document_field(ContactReadingKey.SUPPORT, default=None)
    """
    The name of what the thing rests on, or None where nothing supports it.
    """

    gap: Optional[float] = document_field(ContactReadingKey.GAP, default=None)
    """
    The gap between the bottom of its collision box and the top of its support's, in
    metres, or None without a support.
    """

    size: Optional[Vector3] = document_field(ContactReadingKey.SIZE, default=None)
    """
    The size of its collision box in metres, or None where no box was tested.
    """


class ContactReasoningKey(StrEnum):
    """
    The keys of a working-memory backend's reasoning.
    """

    CONDITION = "condition"
    """
    The condition tested.
    """

    READINGS = "readings"
    """
    The things tested.
    """


@dataclass(kw_only=True)
class ContactReasoning(Reasoning):
    """
    What a working-memory backend read off the twin's geometry.
    """

    condition: Optional[str] = document_field(
        ContactReasoningKey.CONDITION, default=None
    )
    """
    The condition the statement asks of its answers, or None for none.
    """

    readings: List[ContactReading] = document_field(
        ContactReasoningKey.READINGS, default_factory=list
    )
    """
    Every thing tested, in the order it was tested.
    """

    @classmethod
    def source(cls) -> KnowledgeSource:
        return KnowledgeSource.WORKING_MEMORY


class RuleReadingKey(StrEnum):
    """
    The keys of one rule a rules backend walked.
    """

    CONDITION = "condition"
    """
    When the rule fires.
    """

    CONCLUSION = "conclusion"
    """
    What it concludes.
    """

    TRIED = "tried"
    """
    Whether it was tried.
    """

    FIRED = "fired"
    """
    Whether it fired.
    """


@dataclass(kw_only=True)
class RuleReading(JsonDocument):
    """
    One rule of a cascade, and how far the backend got with it.
    """

    condition: str = document_field(RuleReadingKey.CONDITION)
    """
    When the rule fires.
    """

    conclusion: str = document_field(RuleReadingKey.CONCLUSION)
    """
    What the rule concludes.
    """

    tried: bool = document_field(RuleReadingKey.TRIED)
    """
    Whether the backend tried the rule.
    """

    fired: bool = document_field(RuleReadingKey.FIRED)
    """
    Whether the rule fired.
    """


@dataclass(frozen=True)
class PlanarPoint(NumberArray):
    """
    A point on a plane, written as ``[x, y]``.
    """

    x: float
    """
    The x coordinate.
    """

    y: float
    """
    The y coordinate.
    """

    @classmethod
    def length(cls) -> int:
        return 2


class LayoutRegionKey(StrEnum):
    """
    The keys of one region of a layout.
    """

    KIND = "kind"
    """
    The region's kind.
    """

    CENTER = "center"
    """
    Its centre.
    """

    OUTLINE = "outline"
    """
    Its corners.
    """

    CONCLUDED = "concluded"
    """
    Whether the rules concluded it.
    """


@dataclass(kw_only=True)
class LayoutRegion(JsonDocument):
    """
    One region of a layout a rule's conclusion picks from.
    """

    kind: str = document_field(LayoutRegionKey.KIND)
    """
    The region's kind, as the rules name it.
    """

    center: PlanarPoint = document_field(LayoutRegionKey.CENTER)
    """
    The region's centre on the layout, in metres from the layout's centre.
    """

    outline: List[PlanarPoint] = document_field(
        LayoutRegionKey.OUTLINE, default_factory=list
    )
    """
    The region's corners on the layout, in order.
    """

    concluded: bool = document_field(LayoutRegionKey.CONCLUDED, default=False)
    """
    Whether it is of the kind the rules concluded.
    """


class RegionLayoutKey(StrEnum):
    """
    The keys of a layout of regions.
    """

    WIDTH = "width"
    """
    The layout's extent along x.
    """

    LENGTH = "length"
    """
    The layout's extent along y.
    """

    REGIONS = "regions"
    """
    The regions on it.
    """


@dataclass(kw_only=True)
class RegionLayout(JsonDocument):
    """
    A rectangle seen from above with the regions on it, such as a board with its holes.
    """

    width: float = document_field(RegionLayoutKey.WIDTH)
    """
    The extent along x, in metres.
    """

    length: float = document_field(RegionLayoutKey.LENGTH)
    """
    The extent along y, in metres.
    """

    regions: List[LayoutRegion] = document_field(
        RegionLayoutKey.REGIONS, default_factory=list
    )
    """
    The regions on it.
    """


class RuleReasoningKey(StrEnum):
    """
    The keys of a rules backend's reasoning.
    """

    CASE = "case"
    """
    The case the rules were asked about.
    """

    CASE_KIND = "caseKind"
    """
    The case's kind.
    """

    RULES = "rules"
    """
    The cascade.
    """

    LAYOUT = "layout"
    """
    The layout the conclusion picks from.
    """


@dataclass(kw_only=True)
class RuleReasoning(Reasoning):
    """
    The cascade of rules a rules backend walked to the rule that fires.
    """

    case: str = document_field(RuleReasoningKey.CASE)
    """
    The name of the case the rules were asked about.
    """

    case_kind: str = document_field(RuleReasoningKey.CASE_KIND)
    """
    The case's kind, which the rules test.
    """

    rules: List[RuleReading] = document_field(
        RuleReasoningKey.RULES, default_factory=list
    )
    """
    The rules in the order they are tried.
    """

    layout: Optional[RegionLayout] = document_field(
        RuleReasoningKey.LAYOUT, default=None
    )
    """
    The layout whose regions the conclusion picks from, or None for a conclusion about
    no layout.
    """

    @classmethod
    def source(cls) -> KnowledgeSource:
        return KnowledgeSource.RULES


class OutcomeProbabilityKey(StrEnum):
    """
    The keys of the probability of one outcome.
    """

    OUTCOME = "outcome"
    """
    The outcome.
    """

    PROBABILITY = "probability"
    """
    Its probability.
    """


@dataclass(kw_only=True)
class OutcomeProbability(JsonDocument):
    """
    The probability a model gives one outcome.
    """

    outcome: str = document_field(OutcomeProbabilityKey.OUTCOME)
    """
    The outcome.
    """

    probability: float = document_field(OutcomeProbabilityKey.PROBABILITY)
    """
    Its probability, from 0 to 1.
    """


class SamplingReasoningKey(StrEnum):
    """
    The keys of a probabilistic backend's reasoning.
    """

    SUBJECT = "subject"
    """
    What the outcomes are about.
    """

    PRIOR = "prior"
    """
    The distribution sampled.
    """

    SAMPLES = "samples"
    """
    The outcomes drawn.
    """


@dataclass(kw_only=True)
class SamplingReasoning(Reasoning):
    """
    The distribution a probabilistic backend sampled and the outcomes it drew.
    """

    subject: str = document_field(SamplingReasoningKey.SUBJECT)
    """
    The name of what the outcomes are about.
    """

    prior: List[OutcomeProbability] = document_field(
        SamplingReasoningKey.PRIOR, default_factory=list
    )
    """
    Every outcome with its probability, in the order they are drawn side by side.
    """

    samples: List[str] = document_field(
        SamplingReasoningKey.SAMPLES, default_factory=list
    )
    """
    The outcomes drawn, in the order they were drawn.
    """

    @classmethod
    def source(cls) -> KnowledgeSource:
        return KnowledgeSource.PROBABILISTIC


# %% resolutions


class BackendDescriptionKey(StrEnum):
    """
    The keys of a backend open parts are asked of.
    """

    NAME = "name"
    """
    The backend's name.
    """

    SOURCE = "source"
    """
    The knowledge it answers from.
    """


@dataclass(kw_only=True)
class BackendDescription(JsonDocument):
    """
    A backend the open parts of a plan are asked of.
    """

    name: str = document_field(BackendDescriptionKey.NAME)
    """
    The backend's name.
    """

    source: KnowledgeSource = document_field(BackendDescriptionKey.SOURCE)
    """
    The kind of knowledge it answers from.
    """


class ResolvedPartKey(StrEnum):
    """
    The keys of one resolved open part.
    """

    PART = "part"
    """
    The part's name.
    """

    IDENTIFIER = "id"
    """
    The part's identity in the plan's lines.
    """

    STATEMENT = "statement"
    """
    The statement the part was asked as.
    """

    BACKEND = "backend"
    """
    The backend that answered it.
    """

    ANSWERS = "answers"
    """
    The answers.
    """

    EVIDENCE = "evidence"
    """
    What the backend based them on.
    """

    REASONING = "reasoning"
    """
    How it reasoned.
    """

    HIGHLIGHT = "highlight"
    """
    What the scene shows of the answers.
    """

    MILLISECONDS = "milliseconds"
    """
    How long answering took.
    """

    ANSWERED_AT = "answeredAt"
    """
    When it was answered.
    """


@dataclass(kw_only=True)
class ResolvedPart(JsonDocument):
    """
    One open part of a plan, the backend that answered it and how.
    """

    part: str = document_field(ResolvedPartKey.PART)
    """
    The part's name, such as the field of the action it leaves open.
    """

    identifier: str = document_field(ResolvedPartKey.IDENTIFIER)
    """
    The part's identity, which marks it in the plan's lines.
    """

    statement: str = document_field(ResolvedPartKey.STATEMENT)
    """
    The statement the part was asked as.
    """

    backend: BackendDescription = document_field(ResolvedPartKey.BACKEND)
    """
    The backend that answered it.
    """

    answers: List[str] = document_field(ResolvedPartKey.ANSWERS, default_factory=list)
    """
    The answers, the one taken first.
    """

    evidence: List[str] = document_field(ResolvedPartKey.EVIDENCE, default_factory=list)
    """
    What the backend based its answers on, in words.
    """

    reasoning: Optional[Reasoning] = document_field(
        ResolvedPartKey.REASONING, default=None
    )
    """
    How the backend reasoned, or None for a backend that does not say.
    """

    highlight: SceneHighlight = document_field(
        ResolvedPartKey.HIGHLIGHT, default_factory=SceneHighlight
    )
    """
    What the scene shows of the answers.
    """

    milliseconds: float = document_field(ResolvedPartKey.MILLISECONDS, default=0.0)
    """
    How long answering took, in milliseconds.
    """

    answered_at: float = document_field(ResolvedPartKey.ANSWERED_AT)
    """
    When the part was answered, in seconds since the Unix epoch.
    """


class PlanLineKey(StrEnum):
    """
    The keys of one line of a plan's text.
    """

    TEXT = "text"
    """
    The line.
    """

    PART = "part"
    """
    The open part the line states.
    """


@dataclass(kw_only=True)
class PlanLine(JsonDocument):
    """
    One line of a plan's text; an open part within it is marked as ``⟦identifier⟧``.
    """

    text: str = document_field(PlanLineKey.TEXT)
    """
    The line.
    """

    part: Optional[str] = document_field(PlanLineKey.PART, default=None)
    """
    The identity of the open part the line states, or None for a line stating none.
    """


class PlanResolutionKey(StrEnum):
    """
    The keys of the resolution of one plan.
    """

    IDENTIFIER = "id"
    """
    The resolution's identity.
    """

    TITLE = "title"
    """
    What the plan does.
    """

    UNDERSPECIFIED = "underspecified"
    """
    The plan as stated.
    """

    RESOLVED = "resolved"
    """
    The plan as resolved.
    """

    PARTS = "parts"
    """
    The parts answered so far.
    """

    DONE = "done"
    """
    Whether every part was asked.
    """

    EXECUTABLE = "executable"
    """
    Whether the resolved plan can be carried out.
    """


@dataclass(kw_only=True)
class PlanResolution(JsonDocument):
    """
    The resolution of one plan that left parts open.
    """

    identifier: str = document_field(PlanResolutionKey.IDENTIFIER)
    """
    The resolution's identity among the publisher's resolutions.
    """

    title: str = document_field(PlanResolutionKey.TITLE)
    """
    What the plan does.
    """

    underspecified: List[PlanLine] = document_field(
        PlanResolutionKey.UNDERSPECIFIED, default_factory=list
    )
    """
    The plan as stated, its open parts marked.
    """

    resolved: List[PlanLine] = document_field(
        PlanResolutionKey.RESOLVED, default_factory=list
    )
    """
    The plan as resolved, its answered parts marked.
    """

    parts: List[ResolvedPart] = document_field(
        PlanResolutionKey.PARTS, default_factory=list
    )
    """
    The parts answered so far, in the order they were answered.
    """

    done: bool = document_field(PlanResolutionKey.DONE, default=False)
    """
    Whether every open part was asked.
    """

    executable: bool = document_field(PlanResolutionKey.EXECUTABLE, default=False)
    """
    Whether the resolved plan can be carried out on request.
    """


class PresentationKey(StrEnum):
    """
    The keys of how long the viewer takes to show a resolution.
    """

    BEFORE = "beforeMilliseconds"
    """
    Before the first part.
    """

    PART = "partMilliseconds"
    """
    For each part.
    """

    AFTER = "afterMilliseconds"
    """
    After the last part.
    """


@dataclass(kw_only=True)
class ResolutionPresentation(JsonDocument):
    """
    How long the viewer takes to show a resolution, which the robot waits for before
    carrying it out.
    """

    before_milliseconds: float = document_field(PresentationKey.BEFORE, default=1600.0)
    """
    How long the plan as stated is shown before its first part is asked.
    """

    part_milliseconds: float = document_field(PresentationKey.PART, default=4200.0)
    """
    How long each part is shown.
    """

    after_milliseconds: float = document_field(PresentationKey.AFTER, default=2400.0)
    """
    How long the resolved plan is shown after its last part.
    """


class PlanResolutionsKey(StrEnum):
    """
    The keys of every resolution of a publisher.
    """

    BACKENDS = "backends"
    """
    The backends open parts are asked of.
    """

    RESOLUTIONS = "resolutions"
    """
    The resolutions so far.
    """

    PRESENTATION = "presentation"
    """
    How long the viewer takes to show one.
    """


@dataclass(kw_only=True)
class PlanResolutions(JsonDocument):
    """
    Every resolution a running process published.
    """

    backends: List[BackendDescription] = document_field(
        PlanResolutionsKey.BACKENDS, default_factory=list
    )
    """
    The backends open parts are asked of, in the order they are asked.
    """

    resolutions: List[PlanResolution] = document_field(
        PlanResolutionsKey.RESOLUTIONS, default_factory=list
    )
    """
    Every resolution so far, oldest first.
    """

    presentation: ResolutionPresentation = document_field(
        PlanResolutionsKey.PRESENTATION, default_factory=ResolutionPresentation
    )
    """
    How long the viewer takes to show a resolution.
    """


class ExecutionRequestKey(StrEnum):
    """
    The keys of a request to carry out a resolved plan.
    """

    RESOLUTION = "resolution"
    """
    The resolution whose plan is carried out.
    """


@dataclass(kw_only=True)
class ExecutionRequest(JsonDocument):
    """
    A request to carry out the plan a resolution resolved.
    """

    resolution: str = document_field(ExecutionRequestKey.RESOLUTION)
    """
    The identity of the resolution.
    """
