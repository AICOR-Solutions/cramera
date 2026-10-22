"""
Stand-ins for the circuit libraries, so the circuit workbench can be tested where
``probabilistic_model``, ``random_events``, ``krrood`` and ``plotly`` are not installed.

They record what the workbench asks and answer with fixed values.
"""

from __future__ import annotations

import json
import types
from dataclasses import dataclass, field
from enum import Enum, StrEnum

from typing_extensions import Any, Dict, List, Optional, Tuple

from cramera_protocol.models import (
    FigureKey,
    ModelVariable,
    VariableKind,
    WorkbenchStateKey,
)


class MarginalPlotKey(StrEnum):
    """
    The keys of the traces and layouts the mimic's marginals draw.
    """

    NAME = "name"
    """
    A trace's name.
    """

    TITLE = "title"
    """
    A layout's title.
    """


# %% sets and intervals


class BoundMimic(Enum):
    """
    Whether an interval end belongs to the interval.
    """

    OPEN = "open"
    """
    The end is left out.
    """

    CLOSED = "closed"
    """
    The end belongs to the interval.
    """


@dataclass(frozen=True)
class SimpleIntervalMimic:
    """
    One interval between two numbers.
    """

    lower: float
    """
    The lower end.
    """

    upper: float
    """
    The upper end.
    """

    left: BoundMimic = BoundMimic.CLOSED
    """
    Whether the lower end belongs to the interval.
    """

    right: BoundMimic = BoundMimic.CLOSED
    """
    Whether the upper end belongs to the interval.
    """

    @classmethod
    def from_data(
        cls, lower: float, upper: float, left: BoundMimic, right: BoundMimic
    ) -> SimpleIntervalMimic:
        """
        :return: The interval from ``lower`` to ``upper``.
        """
        return cls(lower, upper, left, right)


@dataclass(frozen=True)
class UnionMimic:
    """
    A union of simple sets: intervals, or elements of a symbolic domain.
    """

    simple_sets: Tuple[Any, ...] = ()
    """
    The united simple sets, in the order they were given.
    """

    @classmethod
    def from_simple_sets(cls, *simple_sets: Any) -> UnionMimic:
        """
        :return: The union of ``simple_sets``.
        """
        return cls(tuple(simple_sets))

    def union_with(self, other: UnionMimic) -> UnionMimic:
        """
        :return: This union and ``other`` united.
        """
        return type(self)(self.simple_sets + other.simple_sets)


class IntervalMimic(UnionMimic):
    """
    A union of intervals.
    """


class SetMimic(UnionMimic):
    """
    A selection of elements of a symbolic domain.
    """

    @property
    def all_elements(self) -> Tuple[str, ...]:
        """
        :return: The values of the elements, as a symbolic domain lists them.
        """
        return tuple(element.element for element in self.simple_sets)


@dataclass(frozen=True)
class SetElementMimic:
    """
    One element of a symbolic domain.
    """

    element: str
    """
    The element.
    """

    @classmethod
    def from_data(cls, element: str, all_elements: Tuple[Any, ...]) -> SetElementMimic:
        """
        :return: The element ``element`` of the domain ``all_elements``.
        """
        return cls(element)

    def __str__(self) -> str:
        return self.element


# %% variables


@dataclass(frozen=True)
class VariableMimic:
    """
    A variable of a model.
    """

    name: str
    """
    The variable's name.
    """

    domain: Any = None
    """
    The values the variable may take.
    """


class SymbolicMimic(VariableMimic):
    """
    A variable over named values.
    """


class IntegerMimic(VariableMimic):
    """
    A variable over whole numbers.
    """


class ContinuousMimic(VariableMimic):
    """
    A variable over real numbers.
    """


# %% events


class SimpleEventMimic(dict):
    """
    One assignment per variable.
    """

    @classmethod
    def from_data(cls) -> SimpleEventMimic:
        """
        :return: An event without assignments.
        """
        return cls()


@dataclass
class EventMimic:
    """
    A union of simple events.
    """

    simple_sets: List[SimpleEventMimic] = field(default_factory=list)
    """
    The simple events.
    """

    filled_with: Optional[List[VariableMimic]] = None
    """
    The variables the event was extended to, once it was.
    """

    @classmethod
    def from_simple_sets(cls, *simple_sets: SimpleEventMimic) -> EventMimic:
        """
        :return: The union of ``simple_sets``.
        """
        return cls(list(simple_sets))

    def fill_missing_variables(self, variables: List[VariableMimic]) -> None:
        """
        :param variables: The variables the event must span.
        """
        self.filled_with = list(variables)


# %% models


class SerializationErrorMimic(Exception):
    """
    Data the serializer cannot read.
    """


@dataclass(frozen=True)
class SupportMimic:
    """
    The support of a prior: simple events over one variable.
    """

    simple_sets: List[Dict[VariableMimic, IntervalMimic]]
    """
    The simple events of the support.
    """


@dataclass(frozen=True)
class PriorMimic:
    """
    The prior of one variable.
    """

    support: SupportMimic
    """
    Where the prior is not zero.
    """


@dataclass
class CircuitMimic:
    """
    A model with variables, read from the mimic's own circuit file.
    """

    variables: List[VariableMimic] = field(default_factory=list)
    """
    The model's variables.
    """

    supports: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    """
    The lower and upper end of each numeric variable's prior support.
    """

    @classmethod
    def from_json(cls, data: Any) -> Any:
        """
        :param data: A decoded circuit file of the mimic.
        :return: The model it describes; a list describes no model, but a list.
        :raises SerializationErrorMimic: When the data is an object without
            variables.
        """
        if isinstance(data, list):
            return data
        if WorkbenchStateKey.VARIABLES not in data:
            raise SerializationErrorMimic("the data names no variables")
        return CircuitFileMimic(data).circuit()

    def marginal(self, variables: List[VariableMimic]) -> MarginalMimic:
        """
        :return: The marginal over ``variables``.
        """
        return MarginalMimic(variables)


@dataclass(frozen=True)
class CircuitFileMimic:
    """
    The mimic's circuit file: the variables as the workbench state describes them.
    """

    data: Dict[str, Any]
    """
    The decoded file.
    """

    def circuit(self) -> CircuitMimic:
        """
        :return: The model the file describes.
        """
        circuit = CircuitMimic()
        for entry in self.data[WorkbenchStateKey.VARIABLES]:
            variable = ModelVariable.from_json(entry)
            if variable.kind is VariableKind.SYMBOLIC:
                domain = SetMimic.from_simple_sets(
                    *(SetElementMimic(value) for value in variable.values)
                )
                circuit.variables.append(SymbolicMimic(variable.name, domain))
                continue
            kind = (
                IntegerMimic
                if variable.kind is VariableKind.INTEGER
                else ContinuousMimic
            )
            circuit.variables.append(kind(variable.name, IntervalMimic()))
            circuit.supports[variable.name] = (variable.low, variable.high)
        return circuit


@dataclass(frozen=True)
class MarginalMimic:
    """
    A marginal that draws itself as one trace per variable.
    """

    variables: List[VariableMimic]
    """
    The variables of the marginal.
    """

    def plot(self) -> List[Dict[str, Any]]:
        """
        :return: One trace per variable, named after it.
        """
        return [{MarginalPlotKey.NAME: variable.name} for variable in self.variables]

    def plotly_layout(self) -> Dict[str, Any]:
        """
        :return: A layout titled after the first variable.
        """
        return {MarginalPlotKey.TITLE: self.variables[0].name}


@dataclass
class ControllerMimic:
    """
    Holds a model and records the events of the questions asked; answers with the values
    its fields hold.
    """

    model: Optional[CircuitMimic] = None
    """
    The loaded model.
    """

    variable_map: Dict[str, VariableMimic] = field(default_factory=dict)
    """
    The model's variables by name.
    """

    priors: Dict[VariableMimic, PriorMimic] = field(default_factory=dict)
    """
    The prior of each numeric variable.
    """

    asked: List[Tuple[EventMimic, ...]] = field(default_factory=list)
    """
    The events of every question, in the order they were asked.
    """

    probability: float = 0.25
    """
    The answer to every probability question.
    """

    evidence_possible: bool = True
    """
    Whether posteriors and modes can be conditioned on the evidence.
    """

    likelihood: float = 0.5
    """
    The likelihood of every mode.
    """

    def set_model(self, model: CircuitMimic) -> None:
        """
        :param model: The model to hold.
        """
        self.model = model
        self.variable_map = {variable.name: variable for variable in model.variables}
        self.priors = {
            variable: PriorMimic(
                SupportMimic(
                    [
                        {
                            variable: IntervalMimic.from_simple_sets(
                                SimpleIntervalMimic(*model.supports[variable.name])
                            )
                        }
                    ]
                )
            )
            for variable in model.variables
            if variable.name in model.supports
        }

    def calculate_probability(self, query: EventMimic, evidence: EventMimic) -> float:
        """
        :return: :attr:`probability`.
        """
        self.asked.append((query, evidence))
        return self.probability

    def calculate_posterior(self, evidence: EventMimic) -> Optional[CircuitMimic]:
        """
        :return: The model, or None when the evidence is impossible.
        """
        self.asked.append((evidence,))
        return self.model if self.evidence_possible else None

    def calculate_mode(
        self, evidence: EventMimic
    ) -> Optional[Tuple[EventMimic, float]]:
        """
        :return: A mode assigning each variable its domain's first value or its
            support, with :attr:`likelihood`; None when the evidence is impossible.
        """
        self.asked.append((evidence,))
        if not self.evidence_possible:
            return None
        mode = SimpleEventMimic()
        for variable in self.model.variables:
            if variable in self.priors:
                mode[variable] = self.priors[variable].support.simple_sets[0][variable]
            else:
                mode[variable] = SetMimic.from_simple_sets(
                    variable.domain.simple_sets[0]
                )
        return EventMimic([mode]), self.likelihood


# %% figures


@dataclass(frozen=True)
class FigureMimic:
    """
    A figure of traces and a layout.
    """

    data: List[Dict[str, Any]]
    """
    The traces.
    """

    layout: Dict[str, Any]
    """
    The layout.
    """


def figure_json(figure: FigureMimic) -> str:
    """
    :param figure: A figure.
    :return: Its JSON text with ``data`` and ``layout``.
    """
    return json.dumps({FigureKey.DATA: figure.data, FigureKey.LAYOUT: figure.layout})


# %% modules


@dataclass(frozen=True)
class CircuitLibraryMimic:
    """
    The mimic as the modules the circuit workbench imports.
    """

    def modules(self) -> Dict[str, types.ModuleType]:
        """
        :return: Each module the workbench imports, with its parent packages, by its
            import name.
        """
        members = {
            "plotly.graph_objects": {"Figure": FigureMimic},
            "plotly.io": {"to_json": figure_json},
            "krrood.adapters.exceptions": {
                "JSONSerializationError": SerializationErrorMimic
            },
            "probabilistic_model.gui.controller": {"ModelController": ControllerMimic},
            "probabilistic_model.probabilistic_circuit.rx.probabilistic_circuit": {
                "ProbabilisticCircuit": CircuitMimic
            },
            "random_events.interval": {
                "Bound": BoundMimic,
                "Interval": IntervalMimic,
                "SimpleInterval": SimpleIntervalMimic,
            },
            "random_events.product_algebra": {
                "Event": EventMimic,
                "SimpleEvent": SimpleEventMimic,
            },
            "random_events.set": {"Set": SetMimic, "SetElement": SetElementMimic},
            "random_events.variable": {
                "Integer": IntegerMimic,
                "Symbolic": SymbolicMimic,
                "Variable": VariableMimic,
            },
        }
        modules: Dict[str, types.ModuleType] = {}
        for name, attributes in members.items():
            module = self.module(modules, name)
            vars(module).update(attributes)
        return modules

    def module(
        self, modules: Dict[str, types.ModuleType], name: str
    ) -> types.ModuleType:
        """
        :param modules: The modules created so far, extended in place.
        :param name: A dotted module name.
        :return: The module of that name, created with its parent packages.
        """
        if name in modules:
            return modules[name]
        module = types.ModuleType(name)
        modules[name] = module
        parent, _, child = name.rpartition(".")
        if parent:
            vars(self.module(modules, parent))[child] = module
        return module
