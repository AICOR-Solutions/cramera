"""
The workbench over a probabilistic circuit: loading it from its JSON file, turning
constraint rows into events, and answering probability, posterior and mode questions
through the controller of ``probabilistic_model``'s desktop interface.

This module imports the circuit libraries; it is imported only where
:class:`~cramera_models.libraries.CircuitLibraries` finds them all.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass, field

import plotly.graph_objects as graph_objects
import plotly.io as plotly_io
from krrood.adapters.exceptions import JSONSerializationError
from probabilistic_model.gui.controller import ModelController
from probabilistic_model.probabilistic_circuit.rx.probabilistic_circuit import (
    ProbabilisticCircuit,
)
from random_events.interval import Bound, Interval, SimpleInterval
from random_events.product_algebra import Event, SimpleEvent
from random_events.set import Set, SetElement
from random_events.variable import Integer, Symbolic, Variable
from typing_extensions import Any, Dict, List, Optional

from cramera_models.exceptions import (
    ImpossibleEvidence,
    NoModelLoaded,
    NotACircuit,
    UnknownVariable,
)
from cramera_models.json_text import JsonText
from cramera_models.workbench import Workbench
from cramera_protocol.models import (
    ClosedInterval,
    Constraint,
    ModeAnswer,
    ModelUpload,
    ModelVariable,
    ModeRequest,
    PosteriorAnswer,
    PosteriorRequest,
    ProbabilityAnswer,
    ProbabilityRequest,
    VariableKind,
    WorkbenchState,
)

UNBOUNDED_SUPPORT_LIMIT = 100.0
"""
The bound a numeric variable's range shows where its prior support is infinite, as in
the desktop interface.
"""

POINT_SUPPORT_MARGIN = 1.0
"""
How far a numeric variable's range reaches past a prior support of one point, so the
range has a width.
"""

POINT_RELATIVE_WIDTH = 1e-6
"""
An interval narrower than this, relative to its magnitude, is shown as one value.
"""

SIGNIFICANT_DIGITS = 4
"""
How many significant digits interval ends are shown with.
"""

# %% assignments as text


@dataclass(frozen=True)
class AssignmentText:
    """
    The text of one variable's assignment in a mode: rounded interval ends, a negligible
    interval as its value, and the elements of a symbolic selection.
    """

    assignment: Any
    """
    An :class:`~random_events.interval.Interval` or a :class:`~random_events.set.Set`.
    """

    def text(self) -> str:
        """
        :return: The assignment as people read it.
        """
        if isinstance(self.assignment, Interval):
            return " ∪ ".join(
                self.interval_text(simple) for simple in self.assignment.simple_sets
            )
        return ", ".join(str(element) for element in self.assignment.simple_sets)

    @staticmethod
    def interval_text(interval: SimpleInterval) -> str:
        """
        :param interval: One simple interval.
        :return: ``[low, high]``, or the single value of a negligible interval.
        """
        low, high = float(interval.lower), float(interval.upper)
        magnitude = max(abs(low), abs(high), 1.0)
        if high - low <= magnitude * POINT_RELATIVE_WIDTH:
            return f"{(low + high) / 2:.{SIGNIFICANT_DIGITS}g}"
        return f"[{low:.{SIGNIFICANT_DIGITS}g}, {high:.{SIGNIFICANT_DIGITS}g}]"


# %% workbench


@dataclass
class CircuitWorkbench(Workbench):
    """
    A probabilistic circuit and the questions asked about it.
    """

    controller: ModelController = field(default_factory=ModelController)
    """
    Holds the model, its variables by name and their priors.
    """

    name: Optional[str] = None
    """
    The loaded model's name.
    """

    lock: threading.Lock = field(default_factory=threading.Lock)
    """
    Serializes the requests; the controller is not safe across threads.
    """

    def state(self) -> WorkbenchState:
        with self.lock:
            return self.unlocked_state()

    def unlocked_state(self) -> WorkbenchState:
        """
        :return: The state, read while the caller holds :attr:`lock`.
        """
        if self.controller.model is None:
            return WorkbenchState(loaded=False)
        return WorkbenchState(
            loaded=True,
            name=self.name,
            variables=[
                self.described(variable) for variable in self.controller.model.variables
            ],
        )

    def load(self, upload: ModelUpload) -> WorkbenchState:
        model = self.circuit(upload)
        with self.lock:
            self.controller.set_model(model)
            self.name = upload.name
            return self.unlocked_state()

    def probability(self, request: ProbabilityRequest) -> ProbabilityAnswer:
        with self.lock:
            self.require_model()
            value = self.controller.calculate_probability(
                self.event(request.query), self.event(request.evidence)
            )
        return ProbabilityAnswer(probability=value)

    def posterior(self, request: PosteriorRequest) -> PosteriorAnswer:
        with self.lock:
            self.require_model()
            variables = [self.variable(name) for name in request.variables]
            model = self.controller.calculate_posterior(self.event(request.evidence))
            if model is None:
                raise ImpossibleEvidence()
            figures = {
                variable.name: self.figure(model.marginal([variable]))
                for variable in variables
            }
        return PosteriorAnswer(figures=figures)

    def mode(self, request: ModeRequest) -> ModeAnswer:
        with self.lock:
            self.require_model()
            result = self.controller.calculate_mode(self.event(request.evidence))
        if result is None:
            raise ImpossibleEvidence()
        modes, likelihood = result
        return ModeAnswer(
            likelihood=likelihood,
            modes=[
                {
                    variable.name: AssignmentText(assignment).text()
                    for variable, assignment in simple_event.items()
                }
                for simple_event in modes.simple_sets
            ],
        )

    # %% model

    @staticmethod
    def circuit(upload: ModelUpload) -> ProbabilisticCircuit:
        """
        The circuit serializer raises its own error for data it cannot read; this is the
        one place where it becomes :class:`NotACircuit`.

        :param upload: A model file.
        :return: The circuit it describes.
        :raises InvalidJson: When the file is not JSON.
        :raises NotACircuit: When the file describes no probabilistic circuit.
        """
        data = JsonText(upload.text, upload.name).decode()
        try:
            model = ProbabilisticCircuit.from_json(data)
        except JSONSerializationError as error:
            raise NotACircuit(upload.name, str(error)) from error
        if not isinstance(model, ProbabilisticCircuit):
            raise NotACircuit(upload.name, f"it describes a {type(model).__name__}")
        return model

    def require_model(self) -> None:
        """
        :raises NoModelLoaded: Without a model.
        """
        if self.controller.model is None:
            raise NoModelLoaded()

    def variable(self, name: str) -> Variable:
        """
        :param name: A variable name.
        :return: The model's variable of that name.
        :raises UnknownVariable: When the model has none.
        """
        if name not in self.controller.variable_map:
            raise UnknownVariable(name)
        return self.controller.variable_map[name]

    # %% variables

    def described(self, variable: Variable) -> ModelVariable:
        """
        :param variable: A variable of the model.
        :return: The variable as constraint rows offer it: a symbolic one with its
            values, a numeric one with the range of its prior support.
        """
        if isinstance(variable, Symbolic):
            return ModelVariable(
                name=variable.name,
                kind=VariableKind.SYMBOLIC,
                values=[str(element) for element in variable.domain.all_elements],
            )
        support = self.support_range(variable)
        return ModelVariable(
            name=variable.name,
            kind=(
                VariableKind.INTEGER
                if isinstance(variable, Integer)
                else VariableKind.CONTINUOUS
            ),
            low=support.low,
            high=support.high,
        )

    def support_range(self, variable: Variable) -> ClosedInterval:
        """
        :param variable: A numeric variable of the model.
        :return: The range of its prior support, with infinite ends limited and a
            single point widened.
        """
        support = self.controller.priors[variable].support
        low = float(support.simple_sets[0][variable].simple_sets[0].lower)
        high = float(support.simple_sets[-1][variable].simple_sets[-1].upper)
        low = -UNBOUNDED_SUPPORT_LIMIT if math.isinf(low) else low
        high = UNBOUNDED_SUPPORT_LIMIT if math.isinf(high) else high
        if low == high:
            return ClosedInterval(
                low=low - POINT_SUPPORT_MARGIN, high=high + POINT_SUPPORT_MARGIN
            )
        return ClosedInterval(low=low, high=high)

    # %% events

    def event(self, constraints: List[Constraint]) -> Event:
        """
        :param constraints: Constraint rows; rows on one variable are united.
        :return: The event they describe over every variable of the model, or the
            empty event without rows.
        :raises UnknownVariable: When a row names no variable of the model.
        """
        simple_event = SimpleEvent.from_data()
        for constraint in constraints:
            variable = self.variable(constraint.variable)
            assignment = self.assignment(variable, constraint)
            if variable in simple_event:
                assignment = simple_event[variable].union_with(assignment)
            simple_event[variable] = assignment
        if not simple_event:
            return Event()
        event = Event.from_simple_sets(simple_event)
        event.fill_missing_variables(self.controller.model.variables)
        return event

    @staticmethod
    def assignment(variable: Variable, constraint: Constraint) -> Any:
        """
        :param variable: The constrained variable.
        :param constraint: Its row.
        :return: The selected elements of a symbolic variable; the union of the
            intervals of a numeric one, or its whole domain without intervals.
        """
        if isinstance(variable, Symbolic):
            elements = variable.domain.all_elements
            selected = [
                SetElement.from_data(element, elements)
                for element in elements
                if str(element) in constraint.values
            ]
            return Set.from_simple_sets(*selected)
        if not constraint.intervals:
            return variable.domain
        return Interval.from_simple_sets(
            *(
                SimpleInterval.from_data(
                    min(interval.low, interval.high),
                    max(interval.low, interval.high),
                    Bound.CLOSED,
                    Bound.CLOSED,
                )
                for interval in constraint.intervals
            )
        )

    # %% figures

    @staticmethod
    def figure(marginal: ProbabilisticCircuit) -> Dict[str, Any]:
        """
        :param marginal: A marginal over one variable.
        :return: Its plot as the JSON form of a Plotly figure.
        """
        figure = graph_objects.Figure(marginal.plot(), marginal.plotly_layout())
        return json.loads(plotly_io.to_json(figure))
