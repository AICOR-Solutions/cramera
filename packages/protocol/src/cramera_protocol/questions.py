"""
Questions about a scene: queries in the entity query language, plain-language questions,
ready-made questions, the names a query may use and the knowledge graph.

A live publisher answers them about its running world, the questions plugin of the
viewer about recorded bundles; both answer with the same documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional

from cramera_protocol.bundle.statecharts import Statecharts
from cramera_protocol.document import JsonDocument, document_field, extension_field
from cramera_protocol.version import CURRENT_VERSION, UNVERSIONED, ProtocolVersion

# %% scopes and routes


class QueryScope(StrEnum):
    """
    Which body of knowledge a question is about.
    """

    CURRENT_STATE = "current_state"
    """
    What is true of the world now, or of the recorded scene.
    """

    DETECTED_EVENTS = "detected_events"
    """
    The moments detectors saw during the run.
    """

    EPISODIC_MEMORY = "episodic_memory"
    """
    What finished runs recorded of themselves.
    """


class QuestionsRoute(StrEnum):
    """
    The routes of the questions plugin, below its plugin prefix.
    """

    PRESETS = "presets"
    """
    The ready-made questions about a scene.
    """

    VOCABULARY = "vocabulary"
    """
    The names a query about a scene may use.
    """

    MEMBERS = "members"
    """
    The attributes of one name.
    """

    QUERY = "query"
    """
    Answers a query in the entity query language.
    """

    QUESTION = "question"
    """
    Answers a question in plain language.
    """

    GRAPH = "graph"
    """
    One view of the scene's knowledge graph.
    """


class QuestionsParameter(StrEnum):
    """
    The query parameters of the question routes.
    """

    SCENE = "scene"
    """
    The bundle the question is about.
    """

    SCOPE = "scope"
    """
    The body of knowledge, a :class:`QueryScope` value.
    """

    NAME = "name"
    """
    The name whose members are asked for.
    """

    VIEW = "view"
    """
    The graph view, a :class:`GraphViewName` value.
    """


# %% requests


class QueryRequestKey(StrEnum):
    """
    The keys of a query.
    """

    CODE = "code"
    """
    The query source.
    """

    SCOPE = "scope"
    """
    The body of knowledge asked.
    """

    SCENE = "scene"
    """
    The bundle asked about.
    """


@dataclass(kw_only=True)
class QueryRequest(JsonDocument):
    """
    A query in the entity query language.
    """

    code: str = document_field(QueryRequestKey.CODE)
    """
    The query source; its last expression is the query.
    """

    scope: QueryScope = document_field(
        QueryRequestKey.SCOPE, default=QueryScope.CURRENT_STATE
    )
    """
    The body of knowledge asked.
    """

    scene: Optional[str] = document_field(QueryRequestKey.SCENE, default=None)
    """
    The bundle asked about; live publishers answer about their own world.
    """


class QuestionRequestKey(StrEnum):
    """
    The keys of a plain-language question.
    """

    TEXT = "text"
    """
    The question.
    """

    SCENE = "scene"
    """
    The bundle asked about.
    """


@dataclass(kw_only=True)
class QuestionRequest(JsonDocument):
    """
    A question in plain language, answered by the ready-made question it matches.
    """

    text: str = document_field(QuestionRequestKey.TEXT)
    """
    The question as asked.
    """

    scene: Optional[str] = document_field(QuestionRequestKey.SCENE, default=None)
    """
    The bundle asked about; live publishers answer about their own world.
    """


# %% answers


class VerbalizationKey(StrEnum):
    """
    The keys of a query read back as English.
    """

    TEXT = "text"
    """
    The plain sentence.
    """

    HTML = "html"
    """
    The sentence with its words marked by role.
    """


@dataclass(kw_only=True)
class Verbalization(JsonDocument):
    """
    A query read back as English.
    """

    text: str = document_field(VerbalizationKey.TEXT)
    """
    The plain sentence.
    """

    html: str = document_field(VerbalizationKey.HTML)
    """
    The sentence as HTML, its words marked by the role they play in the query.
    """


class ReplayWindowKey(StrEnum):
    """
    The keys of a stretch of a recording worth replaying.
    """

    START = "start"
    """
    Where the stretch starts.
    """

    END = "end"
    """
    Where the stretch ends.
    """


@dataclass(kw_only=True)
class ReplayWindow(JsonDocument):
    """
    The stretch of a recording worth replaying around an answered moment.
    """

    start: float = document_field(ReplayWindowKey.START)
    """
    The start, in seconds since the epoch.
    """

    end: float = document_field(ReplayWindowKey.END)
    """
    The end, in seconds since the epoch.
    """


class AnswerKind(StrEnum):
    """
    What the rows of an answer are.
    """

    ROWS = "rows"
    """
    Values the query selected.
    """

    ENTITIES = "entities"
    """
    Entities, one per row.
    """


class AnswerColumn(StrEnum):
    """
    The columns an answer row reserves for itself.
    """

    ENTITY = "__entity__"
    """
    The name of the entity a row describes.
    """

    TYPE = "__type__"
    """
    The class name of the entity a row describes.
    """

    VALUE = "value"
    """
    The single value of a row that is no entity.
    """


class QueryAnswerKey(StrEnum):
    """
    The keys of the answer to a query.
    """

    OK = "ok"
    """
    Whether the query could be answered.
    """

    ERROR = "error"
    """
    Why it could not.
    """

    KIND = "kind"
    """
    What the rows are.
    """

    ROWS = "rows"
    """
    The answer rows.
    """

    COUNT = "count"
    """
    How many rows there are.
    """

    MORE = "more"
    """
    Whether rows were left out.
    """

    HIGHLIGHT = "highlight"
    """
    The entities the viewer lights up.
    """

    REPLAY = "replay"
    """
    The replay window of each row.
    """

    VERBALIZATION = "verbalization"
    """
    The query read back as English.
    """


@dataclass(kw_only=True)
class QueryAnswer(JsonDocument):
    """
    The answer to a query, or the reason there is none.
    """

    ok: bool = document_field(QueryAnswerKey.OK, default=True)
    """
    Whether the query could be answered.
    """

    error: Optional[str] = document_field(QueryAnswerKey.ERROR, default=None)
    """
    Why the query could not be answered.
    """

    kind: AnswerKind = document_field(QueryAnswerKey.KIND, default=AnswerKind.ROWS)
    """
    What the rows are.
    """

    rows: List[Dict[str, Any]] = document_field(
        QueryAnswerKey.ROWS, default_factory=list
    )
    """
    The answer rows; columns named by :class:`AnswerColumn` describe the row itself.
    """

    count: int = document_field(QueryAnswerKey.COUNT, default=0)
    """
    How many rows there are.
    """

    more: bool = document_field(QueryAnswerKey.MORE, default=False)
    """
    Whether the answer was cut at its row limit.
    """

    highlight: List[str] = document_field(
        QueryAnswerKey.HIGHLIGHT, default_factory=list
    )
    """
    The keys of the objects and links the viewer lights up, sorted.
    """

    replay: List[Optional[ReplayWindow]] = document_field(
        QueryAnswerKey.REPLAY, default_factory=list
    )
    """
    One entry per row: the stretch worth replaying, or None for a row without a moment.
    """

    verbalization: Optional[Verbalization] = document_field(
        QueryAnswerKey.VERBALIZATION, default=None
    )
    """
    The query read back as English.
    """


# %% ready-made questions


class PresetKey(StrEnum):
    """
    The keys of one ready-made question.
    """

    TEXT = "text"
    """
    The question.
    """

    CODE = "code"
    """
    The query answering it.
    """

    REQUIRES_LIVE = "requires_live"
    """
    Whether it needs a running world.
    """

    SCOPE = "scope"
    """
    The body of knowledge it asks.
    """

    VERBALIZATION = "verbalization"
    """
    Its query read back as English.
    """


@dataclass(kw_only=True)
class PresetDescription(JsonDocument):
    """
    One ready-made question and the query answering it.
    """

    text: str = document_field(PresetKey.TEXT)
    """
    The question as the button shows it.
    """

    code: str = document_field(PresetKey.CODE)
    """
    The query answering it.
    """

    requires_live: bool = document_field(PresetKey.REQUIRES_LIVE, default=False)
    """
    Whether answering it needs a running world.
    """

    scope: QueryScope = document_field(
        PresetKey.SCOPE, default=QueryScope.CURRENT_STATE
    )
    """
    The body of knowledge it asks.
    """

    verbalization: Optional[Verbalization] = document_field(
        PresetKey.VERBALIZATION, default=None
    )
    """
    Its query read back as English, when the query could be built.
    """


class ScopeDescriptionKey(StrEnum):
    """
    The keys of one body of knowledge on offer.
    """

    NAME = "name"
    """
    The scope.
    """

    LABEL = "label"
    """
    The heading its questions are offered under.
    """

    VARIABLES = "variables"
    """
    The variables a query of it may use.
    """


@dataclass(kw_only=True)
class ScopeDescription(JsonDocument):
    """
    One body of knowledge on offer.
    """

    name: QueryScope = document_field(ScopeDescriptionKey.NAME)
    """
    The scope.
    """

    label: str = document_field(ScopeDescriptionKey.LABEL)
    """
    The heading its questions are offered under.
    """

    variables: List[str] = document_field(
        ScopeDescriptionKey.VARIABLES, default_factory=list
    )
    """
    The ready-made variables a query of it may use.
    """


class PresetCatalogKey(StrEnum):
    """
    The keys of the answer listing the ready-made questions.
    """

    OK = "ok"
    """
    Whether the questions could be listed.
    """

    ERROR = "error"
    """
    Why they could not.
    """

    TITLE = "title"
    """
    What the questions are about.
    """

    PRESETS = "presets"
    """
    The questions.
    """

    SCOPES = "scopes"
    """
    The bodies of knowledge on offer.
    """


@dataclass(kw_only=True)
class PresetCatalog(JsonDocument):
    """
    The ready-made questions about a scene and the bodies of knowledge on offer.
    """

    ok: bool = document_field(PresetCatalogKey.OK, default=True)
    """
    Whether the questions could be listed.
    """

    error: Optional[str] = document_field(PresetCatalogKey.ERROR, default=None)
    """
    Why they could not.
    """

    title: str = document_field(PresetCatalogKey.TITLE, default="")
    """
    What the questions are about.
    """

    presets: List[PresetDescription] = document_field(
        PresetCatalogKey.PRESETS, default_factory=list
    )
    """
    The questions, in the order they are offered.
    """

    scopes: List[ScopeDescription] = document_field(
        PresetCatalogKey.SCOPES, default_factory=list
    )
    """
    The bodies of knowledge on offer.
    """


class QuestionMatchKey(StrEnum):
    """
    The keys of the answer to a plain-language question.
    """

    OK = "ok"
    """
    Whether the question could be compared.
    """

    MATCHED = "matched"
    """
    Whether a ready-made question matched.
    """

    SIMILARITY = "similarity"
    """
    How similar the closest ready-made question is.
    """

    REPLY = "reply"
    """
    What to say when nothing matched.
    """

    PRESET = "preset"
    """
    The matching ready-made question.
    """


@dataclass(kw_only=True)
class QuestionMatch(JsonDocument):
    """
    The ready-made question a plain-language question asks, or the reply that none does.
    """

    matched: bool = document_field(QuestionMatchKey.MATCHED)
    """
    Whether a ready-made question matched.
    """

    similarity: float = document_field(QuestionMatchKey.SIMILARITY)
    """
    The similarity between 0 and 100 of the closest ready-made question.
    """

    ok: bool = document_field(QuestionMatchKey.OK, default=True)
    """
    Whether the question could be compared at all.
    """

    reply: Optional[str] = document_field(QuestionMatchKey.REPLY, default=None)
    """
    What to say when nothing matched.
    """

    preset: Optional[PresetDescription] = document_field(
        QuestionMatchKey.PRESET, default=None
    )
    """
    The matching ready-made question.
    """


# %% names a query may use


class VocabularyKind(StrEnum):
    """
    What one name a query may use stands for.
    """

    VARIABLE = "variable"
    """
    A ready-made variable.
    """

    ENTITY_TYPE = "entity_type"
    """
    The type a ready-made variable ranges over.
    """

    CLASS = "class"
    """
    A class of the workspace.
    """

    FACTORY = "factory"
    """
    A keyword of the entity query language.
    """

    VALUE = "value"
    """
    A value put in reach of queries.
    """

    FIELD = "field"
    """
    A dataclass field.
    """

    PROPERTY = "property"
    """
    A property.
    """

    METHOD = "method"
    """
    A method.
    """


class VocabularyEntryKey(StrEnum):
    """
    The keys of one name a query may use.
    """

    NAME = "name"
    """
    The name.
    """

    KIND = "kind"
    """
    What it stands for.
    """

    DETAIL = "detail"
    """
    One line about it.
    """

    MODULE = "module"
    """
    The module defining it.
    """

    TYPE = "type"
    """
    The type whose members follow its dot.
    """

    FURTHER_MODULES = "further_modules"
    """
    How many further modules define a class of the same name.
    """


@dataclass(kw_only=True)
class VocabularyEntry(JsonDocument):
    """
    One name a query may use.
    """

    name: str = document_field(VocabularyEntryKey.NAME)
    """
    The name as a query writes it.
    """

    kind: VocabularyKind = document_field(VocabularyEntryKey.KIND)
    """
    What the name stands for.
    """

    detail: str = document_field(VocabularyEntryKey.DETAIL, default="")
    """
    One line about the name.
    """

    module: str = document_field(VocabularyEntryKey.MODULE, default="")
    """
    The module defining the name, when it has one.
    """

    type_name: str = document_field(VocabularyEntryKey.TYPE, default="")
    """
    The type whose members follow the name's dot, when it has one.
    """

    further_modules: int = document_field(VocabularyEntryKey.FURTHER_MODULES, default=0)
    """
    How many further modules define a class of the same name.
    """


class VocabularyKey(StrEnum):
    """
    The keys of the answer listing the names a query may use.
    """

    OK = "ok"
    """
    Whether the names could be listed.
    """

    ERROR = "error"
    """
    Why they could not.
    """

    NAME = "name"
    """
    The name whose members are listed.
    """

    ENTRIES = "entries"
    """
    The names of a scope.
    """

    MEMBERS = "members"
    """
    The members of one name.
    """


@dataclass(kw_only=True)
class Vocabulary(JsonDocument):
    """
    Every name a query of one scope may use.
    """

    entries: List[VocabularyEntry] = document_field(
        VocabularyKey.ENTRIES, default_factory=list
    )
    """
    The names, variables first.
    """

    ok: bool = document_field(VocabularyKey.OK, default=True)
    """
    Whether the names could be listed.
    """

    error: Optional[str] = document_field(VocabularyKey.ERROR, default=None)
    """
    Why they could not.
    """


@dataclass(kw_only=True)
class Members(JsonDocument):
    """
    The members that may follow one name's dot.
    """

    name: str = document_field(VocabularyKey.NAME, default="")
    """
    The name whose members are listed.
    """

    members: List[VocabularyEntry] = document_field(
        VocabularyKey.MEMBERS, default_factory=list
    )
    """
    The members.
    """

    ok: bool = document_field(VocabularyKey.OK, default=True)
    """
    Whether the members could be listed.
    """

    error: Optional[str] = document_field(VocabularyKey.ERROR, default=None)
    """
    Why they could not.
    """


# %% knowledge graph


class GraphViewName(StrEnum):
    """
    The views of a scene's knowledge graph.
    """

    KNOWLEDGE = "knowledge"
    """
    The scene's entities and how they relate.
    """

    PLAN = "plan"
    """
    The executed plan.
    """

    STATECHART = "chart"
    """
    The motion statecharts of the run.
    """

    KINEMATICS = "kinematics"
    """
    The robot's kinematic tree.
    """


class GraphLayout(StrEnum):
    """
    How the browser lays a graph out.
    """

    FREE = "free"
    """
    A force-directed layout.
    """

    HIERARCHY = "hier"
    """
    A top-down hierarchy.
    """

    HIERARCHY_LEFT_RIGHT = "hier-lr"
    """
    A left-to-right hierarchy.
    """


class GraphEdgeKind(StrEnum):
    """
    How an edge of the knowledge graph is drawn.
    """

    PROPERTY = "property"
    """
    A relation between two entities, drawn solid.
    """

    TYPE = "type"
    """
    A type or dependency relation, drawn dashed.
    """


class GraphNodeKey(StrEnum):
    """
    The keys of one node of a graph view.
    """

    IDENTIFIER = "id"
    """
    The node's identity within the view.
    """

    LABEL = "label"
    """
    The node's label.
    """

    GROUP = "group"
    """
    The node's colour group.
    """

    TITLE = "title"
    """
    The node's tooltip.
    """

    STATUS = "status"
    """
    The node's native status.
    """

    KIND = "kind"
    """
    The class name the node was made from.
    """

    PARENT = "parent"
    """
    The node's parent in a tree.
    """


@dataclass(kw_only=True)
class GraphNode(JsonDocument):
    """
    One node of a graph view.
    """

    identifier: str = document_field(GraphNodeKey.IDENTIFIER)
    """
    The node's identity within the view.
    """

    label: str = document_field(GraphNodeKey.LABEL)
    """
    The node's label.
    """

    group: str = document_field(GraphNodeKey.GROUP)
    """
    The colour group the node is drawn in.
    """

    title: str = document_field(GraphNodeKey.TITLE, default="")
    """
    The node's tooltip.
    """

    status: Optional[str] = document_field(GraphNodeKey.STATUS, default=None)
    """
    The name of the node's native status, for plan and statechart nodes.
    """

    kind: Optional[str] = document_field(GraphNodeKey.KIND, default=None)
    """
    The class name the node was made from, for nodes of a tree.
    """

    parent: Optional[str] = document_field(GraphNodeKey.PARENT, default=None)
    """
    The node's parent, for nodes of a tree.
    """

    extensions: Dict[str, Any] = extension_field()
    """
    Further keys a view wrote.
    """


class GraphEdgeKey(StrEnum):
    """
    The keys of one edge of a graph view.
    """

    SOURCE = "from"
    """
    The node the edge starts at.
    """

    DESTINATION = "to"
    """
    The node the edge leads to.
    """

    KIND = "kind"
    """
    How the edge is drawn.
    """

    LABEL = "label"
    """
    The edge's label.
    """


@dataclass(kw_only=True)
class GraphEdge(JsonDocument):
    """
    One directed edge of a graph view.
    """

    source: str = document_field(GraphEdgeKey.SOURCE)
    """
    The node the edge starts at.
    """

    destination: str = document_field(GraphEdgeKey.DESTINATION)
    """
    The node the edge leads to.
    """

    kind: GraphEdgeKind = document_field(GraphEdgeKey.KIND)
    """
    How the edge is drawn.
    """

    label: str = document_field(GraphEdgeKey.LABEL, default="")
    """
    The relation the edge stands for.
    """


class GraphDetailKey(StrEnum):
    """
    The keys of the details of one graph node.
    """

    LABEL = "label"
    """
    The node's label.
    """

    GROUP = "group"
    """
    The node's colour group.
    """

    LINES = "lines"
    """
    The lines describing the node.
    """


@dataclass(kw_only=True)
class GraphDetail(JsonDocument):
    """
    What the detail panel shows about one node.
    """

    label: str = document_field(GraphDetailKey.LABEL)
    """
    The node's label.
    """

    group: str = document_field(GraphDetailKey.GROUP)
    """
    The node's colour group.
    """

    lines: List[str] = document_field(GraphDetailKey.LINES, default_factory=list)
    """
    The lines describing the node.
    """


class LegendEntryKey(StrEnum):
    """
    The keys of one row of a graph legend.
    """

    GROUP = "group"
    """
    The colour group.
    """

    LABEL = "label"
    """
    What the group stands for.
    """


@dataclass(kw_only=True)
class LegendEntry(JsonDocument):
    """
    One row of a graph view's legend.
    """

    group: str = document_field(LegendEntryKey.GROUP)
    """
    The colour group.
    """

    label: str = document_field(LegendEntryKey.LABEL)
    """
    What the group stands for.
    """


class GraphViewKey(StrEnum):
    """
    The keys of one graph view.
    """

    OK = "ok"
    """
    Whether the view could be built.
    """

    ERROR = "error"
    """
    Why it could not.
    """

    VIEW = "key"
    """
    The view's name.
    """

    NODES = "nodes"
    """
    The nodes.
    """

    EDGES = "edges"
    """
    The edges.
    """

    DETAILS = "details"
    """
    The details per node.
    """

    LEGEND = "legend"
    """
    The legend.
    """

    LAYOUT = "layout"
    """
    How the view is laid out.
    """

    EMPTY = "empty"
    """
    What to say when the view has no nodes.
    """

    RECORDED = "recorded"
    """
    The recorded statecharts, for the statechart view.
    """


@dataclass(kw_only=True)
class GraphView(JsonDocument):
    """
    One view of a scene's knowledge graph.
    """

    view: GraphViewName = document_field(GraphViewKey.VIEW)
    """
    The view's name.
    """

    ok: bool = document_field(GraphViewKey.OK, default=True)
    """
    Whether the view could be built.
    """

    error: Optional[str] = document_field(GraphViewKey.ERROR, default=None)
    """
    Why it could not.
    """

    nodes: List[GraphNode] = document_field(GraphViewKey.NODES, default_factory=list)
    """
    The nodes.
    """

    edges: List[GraphEdge] = document_field(GraphViewKey.EDGES, default_factory=list)
    """
    The edges.
    """

    details: Dict[str, GraphDetail] = document_field(
        GraphViewKey.DETAILS, default_factory=dict
    )
    """
    The details of each node by its identity.
    """

    legend: List[LegendEntry] = document_field(
        GraphViewKey.LEGEND, default_factory=list
    )
    """
    The colour groups the view uses.
    """

    layout: GraphLayout = document_field(GraphViewKey.LAYOUT, default=GraphLayout.FREE)
    """
    How the view is laid out.
    """

    empty: Optional[str] = document_field(GraphViewKey.EMPTY, default=None)
    """
    What to say when the view has no nodes.
    """

    recorded: Optional[Statecharts] = document_field(
        GraphViewKey.RECORDED, default=None
    )
    """
    The recorded statecharts, which the statechart view replays frame by frame.
    """


# %% recorded answers


class RecordedAnswerKey(StrEnum):
    """
    The keys of one recorded answer.
    """

    CODE = "code"
    """
    The query that was answered.
    """

    SCOPE = "scope"
    """
    The body of knowledge it asked.
    """

    ANSWER = "answer"
    """
    The answer.
    """


@dataclass(kw_only=True)
class RecordedAnswer(JsonDocument):
    """
    The answer a ready-made question received when the answers were recorded.
    """

    code: str = document_field(RecordedAnswerKey.CODE)
    """
    The query that was answered.
    """

    scope: QueryScope = document_field(RecordedAnswerKey.SCOPE)
    """
    The body of knowledge it asked.
    """

    answer: QueryAnswer = document_field(RecordedAnswerKey.ANSWER)
    """
    The answer.
    """


class RecordedAnswersKey(StrEnum):
    """
    The keys of a bundle's ``recorded_answers.json``.
    """

    FORMAT_VERSION = "formatVersion"
    """
    The protocol version the answers were written with.
    """

    SCENE = "scene"
    """
    The bundle the answers are about.
    """

    RECORDED_AT = "recordedAt"
    """
    When the answers were recorded.
    """

    PRESETS = "presets"
    """
    The bundle's ready-made questions.
    """

    ANSWERS = "answers"
    """
    The answer of each ready-made question that needs no live run.
    """

    GRAPHS = "graphs"
    """
    Every graph view of the bundle.
    """


@dataclass(kw_only=True)
class RecordedAnswers(JsonDocument):
    """
    The ready-made questions of a bundle, their answers and its graph views, recorded
    where krrood answers them, so a viewer without krrood, such as a static site, can
    show them.
    """

    format_version: ProtocolVersion = document_field(
        RecordedAnswersKey.FORMAT_VERSION, default=UNVERSIONED
    )
    """
    The protocol version the answers were written with.
    """

    scene: str = document_field(RecordedAnswersKey.SCENE)
    """
    The bundle the answers are about.
    """

    recorded_at: str = document_field(RecordedAnswersKey.RECORDED_AT)
    """
    When the answers were recorded, as an ISO 8601 date and time in UTC.
    """

    presets: PresetCatalog = document_field(RecordedAnswersKey.PRESETS)
    """
    The bundle's ready-made questions.
    """

    answers: List[RecordedAnswer] = document_field(
        RecordedAnswersKey.ANSWERS, default_factory=list
    )
    """
    The answer of each ready-made question that needs no live run.
    """

    graphs: List[GraphView] = document_field(
        RecordedAnswersKey.GRAPHS, default_factory=list
    )
    """
    Every graph view of the bundle.
    """

    def __post_init__(self) -> None:
        self.format_version.require_readable_by(CURRENT_VERSION)

    def answer_to(self, code: str, scope: QueryScope) -> Optional[QueryAnswer]:
        """
        :param code: A query.
        :param scope: The body of knowledge it asks.
        :return: The recorded answer, or None when the query was not recorded.
        """
        return next(
            (
                recorded.answer
                for recorded in self.answers
                if recorded.code == code and recorded.scope == scope
            ),
            None,
        )

    def graph(self, view: GraphViewName) -> Optional[GraphView]:
        """
        :param view: A view's name.
        :return: The recorded view, or None when it was not recorded.
        """
        return next((graph for graph in self.graphs if graph.view == view), None)
