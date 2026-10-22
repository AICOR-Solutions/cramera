"""
The probabilistic-models workbench: a probabilistic circuit loaded from its JSON file,
and the probability, posterior and mode questions asked about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Any, Dict, List, Optional

from cramera_protocol.document import JsonDocument, document_field

# %% routes


class ModelsRoute(StrEnum):
    """
    The routes of the models plugin, below ``/api/plugins/models/``.
    """

    STATE = "state"
    """
    Whether a model is loaded, and its variables.
    """

    LOAD = "load"
    """
    Loads a model from the text of its JSON file.
    """

    PROBABILITY = "probability"
    """
    The probability of a query event given evidence.
    """

    POSTERIOR = "posterior"
    """
    The posterior marginals of variables given evidence, as Plotly figures.
    """

    MODE = "mode"
    """
    The most likely assignments given evidence.
    """


# %% variables


class VariableKind(StrEnum):
    """
    The kinds of variables a model has.
    """

    SYMBOLIC = "symbolic"
    """
    A variable over a finite set of named values.
    """

    INTEGER = "integer"
    """
    A variable over whole numbers.
    """

    CONTINUOUS = "continuous"
    """
    A variable over real numbers.
    """


class ModelVariableKey(StrEnum):
    """
    The keys of one variable of a loaded model.
    """

    NAME = "name"
    """
    The variable's name.
    """

    KIND = "kind"
    """
    A :class:`VariableKind` value.
    """

    VALUES = "values"
    """
    The values of a symbolic variable.
    """

    LOW = "low"
    """
    The lowest value of a numeric variable's prior support.
    """

    HIGH = "high"
    """
    The highest value of a numeric variable's prior support.
    """


@dataclass(kw_only=True)
class ModelVariable(JsonDocument):
    """
    One variable as constraints can name it.
    """

    name: str = document_field(ModelVariableKey.NAME)
    """
    The variable's name.
    """

    kind: VariableKind = document_field(ModelVariableKey.KIND)
    """
    The kind of values the variable takes.
    """

    values: List[str] = document_field(ModelVariableKey.VALUES, default_factory=list)
    """
    The values of a symbolic variable; empty for a numeric one.
    """

    low: Optional[float] = document_field(ModelVariableKey.LOW, default=None)
    """
    The lowest value of a numeric variable's prior support, finite; None for a symbolic
    variable.
    """

    high: Optional[float] = document_field(ModelVariableKey.HIGH, default=None)
    """
    The highest value of a numeric variable's prior support, finite; None for a symbolic
    variable.
    """


class WorkbenchStateKey(StrEnum):
    """
    The keys of the answer to :attr:`ModelsRoute.STATE`.
    """

    LOADED = "loaded"
    """
    Whether a model is loaded.
    """

    NAME = "name"
    """
    The loaded model's name.
    """

    VARIABLES = "variables"
    """
    The loaded model's variables.
    """


@dataclass(kw_only=True)
class WorkbenchState(JsonDocument):
    """
    What the workbench holds.
    """

    loaded: bool = document_field(WorkbenchStateKey.LOADED)
    """
    Whether a model is loaded.
    """

    name: Optional[str] = document_field(WorkbenchStateKey.NAME, default=None)
    """
    The loaded model's name, usually its file name; None without a model.
    """

    variables: List[ModelVariable] = document_field(
        WorkbenchStateKey.VARIABLES, default_factory=list
    )
    """
    The loaded model's variables, in the model's order.
    """


# %% loading


class ModelUploadKey(StrEnum):
    """
    The keys of the request to :attr:`ModelsRoute.LOAD`.
    """

    NAME = "name"
    """
    The model's name.
    """

    TEXT = "text"
    """
    The model file's text.
    """


@dataclass(kw_only=True)
class ModelUpload(JsonDocument):
    """
    A model file sent to the workbench.

    The file travels as text because circuit files may hold ``Infinity`` and ``NaN``,
    which Python's JSON reader accepts and the browser's does not.
    """

    name: str = document_field(ModelUploadKey.NAME)
    """
    The model's name, usually its file name.
    """

    text: str = document_field(ModelUploadKey.TEXT)
    """
    The text of the circuit's JSON file.
    """


# %% constraints


class IntervalKey(StrEnum):
    """
    The keys of a closed interval.
    """

    LOW = "low"
    """
    The interval's lower end.
    """

    HIGH = "high"
    """
    The interval's upper end.
    """


@dataclass(kw_only=True)
class ClosedInterval(JsonDocument):
    """
    The numbers from :attr:`low` to :attr:`high`, both included.
    """

    low: float = document_field(IntervalKey.LOW)
    """
    The interval's lower end.
    """

    high: float = document_field(IntervalKey.HIGH)
    """
    The interval's upper end.
    """


class ConstraintKey(StrEnum):
    """
    The keys of one constraint of an event.
    """

    VARIABLE = "variable"
    """
    The constrained variable.
    """

    INTERVALS = "intervals"
    """
    The intervals a numeric variable lies in.
    """

    VALUES = "values"
    """
    The values a symbolic variable takes.
    """


@dataclass(kw_only=True)
class Constraint(JsonDocument):
    """
    One row of an event: a variable and the values it may take.

    Several constraints on one variable are united.
    """

    variable: str = document_field(ConstraintKey.VARIABLE)
    """
    The constrained variable's name.
    """

    intervals: List[ClosedInterval] = document_field(
        ConstraintKey.INTERVALS, default_factory=list
    )
    """
    The intervals a numeric variable lies in; empty for its whole domain.
    """

    values: List[str] = document_field(ConstraintKey.VALUES, default_factory=list)
    """
    The values a symbolic variable takes; empty for none of them.
    """


# %% questions


class ModelRequestKey(StrEnum):
    """
    The keys of the questions asked about a loaded model.
    """

    QUERY = "query"
    """
    The event whose probability is asked for.
    """

    EVIDENCE = "evidence"
    """
    The event that is known to have happened.
    """

    VARIABLES = "variables"
    """
    The variables whose posterior marginals are asked for.
    """


@dataclass(kw_only=True)
class ProbabilityRequest(JsonDocument):
    """
    Asks for ``P(query | evidence)``.
    """

    query: List[Constraint] = document_field(
        ModelRequestKey.QUERY, default_factory=list
    )
    """
    The constraints of the query event; none for the certain event.
    """

    evidence: List[Constraint] = document_field(
        ModelRequestKey.EVIDENCE, default_factory=list
    )
    """
    The constraints of the evidence event; none for no evidence.
    """


@dataclass(kw_only=True)
class PosteriorRequest(JsonDocument):
    """
    Asks for the posterior marginal of each named variable given evidence.
    """

    variables: List[str] = document_field(ModelRequestKey.VARIABLES)
    """
    The names of the variables whose marginals are asked for.
    """

    evidence: List[Constraint] = document_field(
        ModelRequestKey.EVIDENCE, default_factory=list
    )
    """
    The constraints of the evidence event; none for no evidence.
    """


@dataclass(kw_only=True)
class ModeRequest(JsonDocument):
    """
    Asks for the most likely assignments given evidence.
    """

    evidence: List[Constraint] = document_field(
        ModelRequestKey.EVIDENCE, default_factory=list
    )
    """
    The constraints of the evidence event; none for no evidence.
    """


class ModelAnswerKey(StrEnum):
    """
    The keys of the answers about a loaded model.
    """

    PROBABILITY = "probability"
    """
    The asked probability.
    """

    FIGURES = "figures"
    """
    The posterior marginals as Plotly figures, by variable name.
    """

    LIKELIHOOD = "likelihood"
    """
    The likelihood of the most likely assignments.
    """

    MODES = "modes"
    """
    The most likely assignments.
    """


@dataclass(kw_only=True)
class ProbabilityAnswer(JsonDocument):
    """
    The answer to a :class:`ProbabilityRequest`.
    """

    probability: float = document_field(ModelAnswerKey.PROBABILITY)
    """
    ``P(query | evidence)``.
    """


@dataclass(kw_only=True)
class PosteriorAnswer(JsonDocument):
    """
    The answer to a :class:`PosteriorRequest`.
    """

    figures: Dict[str, Any] = document_field(ModelAnswerKey.FIGURES)
    """
    The posterior marginal of each asked variable as a Plotly figure with ``data`` and
    ``layout``, by variable name.
    """


@dataclass(kw_only=True)
class ModeAnswer(JsonDocument):
    """
    The answer to a :class:`ModeRequest`.
    """

    likelihood: float = document_field(ModelAnswerKey.LIKELIHOOD)
    """
    The likelihood of the most likely assignments.
    """

    modes: List[Dict[str, str]] = document_field(ModelAnswerKey.MODES)
    """
    The most likely assignments, each the text of every variable's values by variable
    name.
    """
