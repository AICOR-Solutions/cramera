"""
The queries a running process asks while it sets up, resolves and carries out its plans,
one step each, and the requests that hold it at each query until a person moves on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.questions import Verbalization
from cramera_protocol.resolutions import BackendDescription, Reasoning, SceneHighlight

# %% where a process is held


class StepMoment(StrEnum):
    """
    How far a query had come when the process was held at it.
    """

    ASKED = "asked"
    """
    The query was asked and nothing answered it yet.
    """

    ANSWERED = "answered"
    """
    The query's answering ended.
    """


class HeldStepKey(StrEnum):
    """
    The keys of the step a process is held at.
    """

    NUMBER = "number"
    """
    The query's place among every query asked.
    """

    MOMENT = "moment"
    """
    How far the query had come.
    """


@dataclass(kw_only=True)
class HeldStep(JsonDocument):
    """
    A query a process is held at, and how far it had come.
    """

    number: int = document_field(HeldStepKey.NUMBER)
    """
    The query's place among every query the process asked, from 0.
    """

    moment: StepMoment = document_field(HeldStepKey.MOMENT)
    """
    How far the query had come.
    """


# %% what a step is asked inside


class StepPhase(StrEnum):
    """
    What the process was doing when it asked a query.
    """

    SETUP = "setup"
    """
    Setting up the world and the robot, before any plan exists.
    """

    RESOLUTION = "resolution"
    """
    Answering the parts a plan leaves open, before the robot moves.
    """

    EXPANSION = "expansion"
    """
    Expanding a resolved plan into the motions that carry it out.
    """

    EXECUTION = "execution"
    """
    Carrying a plan out.
    """


class VariableRole(StrEnum):
    """
    What a variable is to its query, or a part to its statement.
    """

    SOUGHT = "sought"
    """
    What the query answers with.
    """

    RANGES_OVER = "ranges over"
    """
    A variable whose values the query tries while it looks for answers.
    """

    GIVEN = "given"
    """
    A value the code asking the query fixed.
    """

    OPEN = "open"
    """
    A part left open for a backend to answer.
    """

    BEING_ANSWERED = "being answered"
    """
    An open part whose answering is under way.
    """

    ANSWERED = "answered"
    """
    An open part a backend answered.
    """


class QueryVariableKey(StrEnum):
    """
    The keys of a variable of a query.
    """

    NAME = "name"
    """
    The variable's name.
    """

    ROLE = "role"
    """
    What it is to the query.
    """

    TYPE = "type"
    """
    The type it states.
    """

    VALUES = "values"
    """
    What it holds.
    """

    LOOKED_AT = "lookedAt"
    """
    How many values the query looked at.
    """


@dataclass(kw_only=True)
class QueryVariable(JsonDocument):
    """
    A variable of a query or a part of a statement, and what it holds.
    """

    name: str = document_field(QueryVariableKey.NAME)
    """
    The name the code gives it, else the part of the statement it is.
    """

    role: VariableRole = document_field(QueryVariableKey.ROLE)
    """
    What it is to the query or statement.
    """

    type_name: Optional[str] = document_field(QueryVariableKey.TYPE, default=None)
    """
    The name of the type it states, or None for a variable stating none.
    """

    values: List[str] = document_field(QueryVariableKey.VALUES, default_factory=list)
    """
    What it holds, in words.
    """

    looked_at: Optional[int] = document_field(QueryVariableKey.LOOKED_AT, default=None)
    """
    How many values the query looked at, or None where it did not count them.
    """


class EnclosingKind(StrEnum):
    """
    The statements a query can be asked inside.
    """

    PLAN = "plan being resolved"
    """
    A plan stated with parts left open.
    """

    ACTION = "action"
    """
    An action being expanded into motions or carried out.
    """

    MOTION = "motion"
    """
    A motion being turned into what carries it out.
    """


class EnclosingStatementKey(StrEnum):
    """
    The keys of a statement a query is asked inside.
    """

    KIND = "kind"
    """
    What kind of statement it is.
    """

    TITLE = "title"
    """
    What it is.
    """

    STATEMENT = "statement"
    """
    What it states.
    """

    PARTS = "parts"
    """
    Its parts.
    """


@dataclass(kw_only=True)
class EnclosingStatement(JsonDocument):
    """
    A statement the process is answering or carrying out while it asks a query.
    """

    kind: EnclosingKind = document_field(EnclosingStatementKey.KIND)
    """
    What kind of statement it is.
    """

    title: str = document_field(EnclosingStatementKey.TITLE)
    """
    What it is, as said to a person.
    """

    statement: Optional[str] = document_field(
        EnclosingStatementKey.STATEMENT, default=None
    )
    """
    What it states in English, or None where it is not written as a statement.
    """

    parts: List[QueryVariable] = document_field(
        EnclosingStatementKey.PARTS, default_factory=list
    )
    """
    Its parts, each given, answered, being answered or open.
    """


# %% where a step is written


class SourceExcerptKey(StrEnum):
    """
    The keys of the lines a query is written in.
    """

    FILE = "file"
    """
    The file.
    """

    FUNCTION = "function"
    """
    The function.
    """

    FIRST_LINE = "firstLine"
    """
    The number of the first line shown.
    """

    LINES = "lines"
    """
    The lines shown.
    """

    FOCUS_FIRST_LINE = "focusFirstLine"
    """
    The first line of the statement in focus.
    """

    FOCUS_LAST_LINE = "focusLastLine"
    """
    The last line of the statement in focus.
    """


@dataclass(kw_only=True)
class SourceExcerpt(JsonDocument):
    """
    The lines a query is written in, the statement writing it in focus.
    """

    file: str = document_field(SourceExcerptKey.FILE)
    """
    The file, relative to the root of its repository where it lies in one.
    """

    function: str = document_field(SourceExcerptKey.FUNCTION)
    """
    The function the statement is in.
    """

    first_line: int = document_field(SourceExcerptKey.FIRST_LINE)
    """
    The number of the first line shown, from 1.
    """

    lines: List[str] = document_field(SourceExcerptKey.LINES, default_factory=list)
    """
    The lines shown.
    """

    focus_first_line: int = document_field(SourceExcerptKey.FOCUS_FIRST_LINE)
    """
    The number of the first line of the statement in focus.
    """

    focus_last_line: int = document_field(SourceExcerptKey.FOCUS_LAST_LINE)
    """
    The number of the last line of the statement in focus.
    """


class CallSiteKey(StrEnum):
    """
    The keys of the call that asked a query.
    """

    FUNCTION = "function"
    """
    The calling function.
    """

    MODULE = "module"
    """
    Its module.
    """

    LINE = "line"
    """
    The line of the call.
    """


@dataclass(kw_only=True)
class CallSite(JsonDocument):
    """
    The call that asked a query.
    """

    function: str = document_field(CallSiteKey.FUNCTION)
    """
    The name of the calling function.
    """

    module: str = document_field(CallSiteKey.MODULE)
    """
    The name of its module.
    """

    line: int = document_field(CallSiteKey.LINE)
    """
    The number of the line of the call.
    """


# %% steps


class QueryStepKey(StrEnum):
    """
    The keys of one query a process asked.
    """

    NUMBER = "number"
    """
    The query's place among every query asked.
    """

    ASKER = "asker"
    """
    The query whose answering asked it.
    """

    DEPTH = "depth"
    """
    How many queries it is asked inside.
    """

    PHASE = "phase"
    """
    What the process was doing.
    """

    DURING = "during"
    """
    The plan or action under way.
    """

    MOMENT = "moment"
    """
    How far the query has come.
    """

    QUESTION = "question"
    """
    The query read back as English.
    """

    CODE = "code"
    """
    The lines writing the query.
    """

    CALLER = "caller"
    """
    The call that asked it.
    """

    BACKEND = "backend"
    """
    The backend answering it.
    """

    GENERATES = "generates"
    """
    Whether the backend generates what the query leaves open.
    """

    ANSWERS = "answers"
    """
    Its answers.
    """

    HIGHLIGHT = "highlight"
    """
    What the scene shows of the answers.
    """

    REASONING = "reasoning"
    """
    How the backend reasoned.
    """

    VARIABLES = "variables"
    """
    The query's variables.
    """

    ENCLOSING = "enclosing"
    """
    The statements it is asked inside.
    """

    MILLISECONDS = "milliseconds"
    """
    How long answering took.
    """


@dataclass(kw_only=True)
class QueryStep(JsonDocument):
    """
    One query a process asked: where, what it asks, what answers it and its answers.
    """

    number: int = document_field(QueryStepKey.NUMBER)
    """
    The query's place among every query the process asked, from 0.
    """

    asker: Optional[int] = document_field(QueryStepKey.ASKER, default=None)
    """
    The number of the query whose answering asked this one, or None for a query asked by
    the process itself.
    """

    depth: int = document_field(QueryStepKey.DEPTH, default=0)
    """
    How many queries this one is asked inside.
    """

    phase: StepPhase = document_field(QueryStepKey.PHASE)
    """
    What the process was doing when it asked the query.
    """

    during: str = document_field(QueryStepKey.DURING)
    """
    The plan or action under way, as said to a person.
    """

    moment: StepMoment = document_field(QueryStepKey.MOMENT)
    """
    How far the query has come.
    """

    question: Optional[Verbalization] = document_field(
        QueryStepKey.QUESTION, default=None
    )
    """
    The query read back as English, or None where it could not be worded.
    """

    code: Optional[SourceExcerpt] = document_field(QueryStepKey.CODE, default=None)
    """
    The lines writing the query, or None where they cannot be read.
    """

    caller: Optional[CallSite] = document_field(QueryStepKey.CALLER, default=None)
    """
    The call that asked the query, or None where it is unknown.
    """

    backend: BackendDescription = document_field(QueryStepKey.BACKEND)
    """
    The backend answering the query.
    """

    generates: bool = document_field(QueryStepKey.GENERATES, default=False)
    """
    Whether the backend generates what the query leaves open rather than looking it up.
    """

    answers: List[str] = document_field(QueryStepKey.ANSWERS, default_factory=list)
    """
    The answers in words, once answered.
    """

    highlight: SceneHighlight = document_field(
        QueryStepKey.HIGHLIGHT, default_factory=SceneHighlight
    )
    """
    What the scene shows of the answers.
    """

    reasoning: Optional[Reasoning] = document_field(
        QueryStepKey.REASONING, default=None
    )
    """
    How the backend reasoned, or None for a backend that does not say.
    """

    variables: List[QueryVariable] = document_field(
        QueryStepKey.VARIABLES, default_factory=list
    )
    """
    The query's variables, what it seeks first.
    """

    enclosing: List[EnclosingStatement] = document_field(
        QueryStepKey.ENCLOSING, default_factory=list
    )
    """
    The statements the query is asked inside, outermost first.
    """

    milliseconds: Optional[float] = document_field(
        QueryStepKey.MILLISECONDS, default=None
    )
    """
    How long answering took in milliseconds, or None before it ended.
    """


class QueryStepsKey(StrEnum):
    """
    The keys of every query a process asked.
    """

    REVISION = "revision"
    """
    How often the steps were published.
    """

    UNCHANGED = "unchanged"
    """
    Whether the steps are those of the revision the viewer named.
    """

    STEPPING = "stepping"
    """
    Whether the process is held at every query.
    """

    HOLDS_NESTED = "holdsNested"
    """
    Whether it is also held at nested queries.
    """

    HELD = "held"
    """
    The step it is held at.
    """

    STEPS = "steps"
    """
    Every query asked.
    """


@dataclass(kw_only=True)
class QuerySteps(JsonDocument):
    """
    Every query a process asked, and the step it is held at.
    """

    revision: int = document_field(QueryStepsKey.REVISION, default=0)
    """
    How often the steps were published, so a viewer can ask only for a newer revision.
    """

    unchanged: bool = document_field(QueryStepsKey.UNCHANGED, default=False)
    """
    Whether the steps are left out because the viewer named the current revision.
    """

    stepping: bool = document_field(QueryStepsKey.STEPPING, default=False)
    """
    Whether the process is held at every query until a person moves on.
    """

    holds_nested: bool = document_field(QueryStepsKey.HOLDS_NESTED, default=True)
    """
    Whether, while stepping, it is also held at queries asked while another is answered.
    """

    held: Optional[HeldStep] = document_field(QueryStepsKey.HELD, default=None)
    """
    The step the process is held at, or None while it runs on.
    """

    steps: List[QueryStep] = document_field(QueryStepsKey.STEPS, default_factory=list)
    """
    Every query asked, in the order asked.
    """


# %% requests


class StepAdvanceKey(StrEnum):
    """
    The keys of a request to let a held process carry on.
    """

    HELD = "held"
    """
    The step the viewer saw the process held at.
    """


@dataclass(kw_only=True)
class StepAdvance(JsonDocument):
    """
    A request to let a held process carry on from the step it is held at.
    """

    held: Optional[HeldStep] = document_field(StepAdvanceKey.HELD, default=None)
    """
    The step the viewer saw the process held at; the process carries on only while it is
    still held there, so a second request cannot skip a step the viewer has not seen.

    None lets it carry on from whatever step it is held at.
    """


class SteppingRequestKey(StrEnum):
    """
    The keys of a request to change how a process is held.
    """

    STEPPING = "stepping"
    """
    Whether it is held at every query.
    """

    HOLDS_NESTED = "holdsNested"
    """
    Whether it is also held at nested queries.
    """


@dataclass(kw_only=True)
class SteppingRequest(JsonDocument):
    """
    A request to change whether a process is held at every query it asks.
    """

    stepping: bool = document_field(SteppingRequestKey.STEPPING)
    """
    Whether the process is held at every query until a person moves on.
    """

    holds_nested: bool = document_field(SteppingRequestKey.HOLDS_NESTED, default=True)
    """
    Whether it is also held at queries asked while another is answered.
    """
