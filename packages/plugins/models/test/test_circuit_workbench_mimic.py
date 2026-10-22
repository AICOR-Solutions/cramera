"""
The circuit workbench against stand-ins of the circuit libraries, so it is tested where
they are not installed: what it reads from a model, the events it builds from constraint
rows, and how it turns the controller's answers into documents.

``test_circuit_workbench`` tests the same behaviour with the real libraries.
"""

from __future__ import annotations

import json

import pytest

from cramera_models.exceptions import (
    ImpossibleEvidence,
    InvalidJson,
    NoModelLoaded,
    NotACircuit,
    UnknownVariable,
)
from cramera_protocol.models import (
    FigureKey,
    ModelVariable,
    ModeRequest,
    PosteriorRequest,
    ProbabilityRequest,
    VariableKind,
    WorkbenchState,
    WorkbenchStateKey,
)

from .dataset.circuit_library_mimic import (
    BoundMimic,
    EventMimic,
    IntervalMimic,
    MarginalPlotKey,
    SetElementMimic,
    SetMimic,
    SimpleIntervalMimic,
)

CIRCUIT = "mimic_circuit.json"
"""
The mimic's circuit file.
"""


@pytest.fixture
def described(dataset):
    """
    :return: The variables of the mimic's circuit file by name, as the file
        describes them.
    """
    data = json.loads((dataset / CIRCUIT).read_text(encoding="utf-8"))
    variables = [
        ModelVariable.from_json(entry) for entry in data[WorkbenchStateKey.VARIABLES]
    ]
    return {variable.name: variable for variable in variables}


@pytest.fixture
def workbench(mimic_workbench_module, upload_of):
    """
    :return: A circuit workbench with the mimic's circuit loaded.
    """
    workbench = mimic_workbench_module.CircuitWorkbench()
    workbench.load(upload_of(CIRCUIT))
    return workbench


def asked(question, name, document_class):
    """
    :param question: Reads a request body of the dataset.
    :param name: The body's file name.
    :param document_class: The request document.
    :return: The request.
    """
    return document_class.from_json(json.loads(question(name)))


def variable_of(workbench, name):
    """
    :param workbench: A workbench with a model.
    :param name: A variable name.
    :return: The model's variable.
    """
    return workbench.controller.variable_map[name]


# %% state


def test_an_empty_workbench_has_no_model(mimic_workbench_module):
    state = mimic_workbench_module.CircuitWorkbench().state()
    assert state == WorkbenchState(loaded=False)


def test_symbolic_and_bounded_variables_are_described_as_the_model_has_them(
    workbench, described
):
    state = workbench.state()
    variables = {variable.name: variable for variable in state.variables}
    assert variables["color"] == described["color"]
    assert variables["x"] == described["x"]


def test_a_point_support_is_widened(mimic_workbench_module, workbench, described):
    count = {variable.name: variable for variable in workbench.state().variables}[
        "count"
    ]
    margin = mimic_workbench_module.POINT_SUPPORT_MARGIN
    assert count.kind == VariableKind.INTEGER
    assert (count.low, count.high) == (
        described["count"].low - margin,
        described["count"].high + margin,
    )


def test_an_infinite_support_is_limited(mimic_workbench_module, workbench):
    distance = {variable.name: variable for variable in workbench.state().variables}[
        "distance"
    ]
    limit = mimic_workbench_module.UNBOUNDED_SUPPORT_LIMIT
    assert (distance.low, distance.high) == (-limit, limit)


@pytest.mark.parametrize(
    "file, error",
    [
        ("questions/not_json.txt", InvalidJson),
        ("object_without_circuit.json", NotACircuit),
        ("list_instead_of_circuit.json", NotACircuit),
    ],
)
def test_a_file_without_a_circuit_is_refused(
    mimic_workbench_module, upload_of, file, error
):
    with pytest.raises(error):
        mimic_workbench_module.CircuitWorkbench().load(upload_of(file))


def test_questions_without_a_model_are_refused(mimic_workbench_module):
    with pytest.raises(NoModelLoaded):
        mimic_workbench_module.CircuitWorkbench().probability(ProbabilityRequest())


# %% events


def test_rows_become_an_event_over_every_variable(workbench, question):
    answer = workbench.probability(
        asked(question, "probability_of_low_x_given_red.json", ProbabilityRequest)
    )
    query, evidence = workbench.controller.asked[-1]
    x = variable_of(workbench, "x")
    color = variable_of(workbench, "color")
    assert answer.probability == workbench.controller.probability
    assert query.simple_sets == [
        {
            x: IntervalMimic(
                (SimpleIntervalMimic(0.0, 0.25, BoundMimic.CLOSED, BoundMimic.CLOSED),)
            )
        }
    ]
    assert evidence.simple_sets == [{color: SetMimic((SetElementMimic("red"),))}]
    assert query.filled_with == workbench.controller.model.variables


def test_rows_on_one_variable_are_united_with_their_ends_ordered(workbench, question):
    workbench.probability(
        asked(question, "probability_of_two_x_rows.json", ProbabilityRequest)
    )
    query, evidence = workbench.controller.asked[-1]
    x = variable_of(workbench, "x")
    assert query.simple_sets[0][x] == IntervalMimic(
        (
            SimpleIntervalMimic(0.0, 0.1, BoundMimic.CLOSED, BoundMimic.CLOSED),
            SimpleIntervalMimic(0.8, 0.9, BoundMimic.CLOSED, BoundMimic.CLOSED),
        )
    )
    assert evidence == EventMimic()


def test_a_row_without_intervals_is_the_whole_domain(workbench, question):
    workbench.probability(
        asked(question, "probability_of_any_x.json", ProbabilityRequest)
    )
    query, _ = workbench.controller.asked[-1]
    x = variable_of(workbench, "x")
    assert query.simple_sets[0][x] is x.domain


def test_an_unknown_variable_is_refused(workbench, question):
    with pytest.raises(UnknownVariable) as refused:
        workbench.probability(
            asked(question, "probability_of_unknown_variable.json", ProbabilityRequest)
        )
    assert refused.value.name == "temperature"


# %% posterior and mode


def test_each_asked_variable_gets_its_marginal_figure(workbench, question):
    request = asked(question, "posterior_of_x_and_color.json", PosteriorRequest)
    answer = workbench.posterior(request)
    assert {
        name: figure[FigureKey.LAYOUT][MarginalPlotKey.TITLE]
        for name, figure in answer.figures.items()
    } == {name: name for name in request.variables}


def test_a_posterior_of_an_unknown_variable_is_refused(workbench, question):
    with pytest.raises(UnknownVariable):
        workbench.posterior(
            asked(question, "posterior_of_unknown_variable.json", PosteriorRequest)
        )


@pytest.mark.parametrize(
    "ask, question_file, request_class",
    [
        (
            lambda workbench: workbench.posterior,
            "posterior_given_impossible_evidence.json",
            PosteriorRequest,
        ),
        (
            lambda workbench: workbench.mode,
            "mode_given_impossible_evidence.json",
            ModeRequest,
        ),
    ],
)
def test_impossible_evidence_is_refused(
    workbench, question, ask, question_file, request_class
):
    workbench.controller.evidence_possible = False
    with pytest.raises(ImpossibleEvidence):
        ask(workbench)(asked(question, question_file, request_class))


def test_a_mode_is_shown_as_text(
    mimic_workbench_module, workbench, question, described
):
    answer = workbench.mode(asked(question, "mode_without_evidence.json", ModeRequest))
    count = described["count"]
    assert answer.likelihood == workbench.controller.likelihood
    assert answer.modes[0]["color"] == described["color"].values[0]
    assert (
        answer.modes[0]["x"]
        == mimic_workbench_module.AssignmentText(
            IntervalMimic.from_simple_sets(
                SimpleIntervalMimic(described["x"].low, described["x"].high)
            )
        ).text()
    )
    assert answer.modes[0]["count"] == f"{count.low:g}"


def test_an_interval_is_shown_with_rounded_ends(mimic_workbench_module):
    text = mimic_workbench_module.AssignmentText(
        IntervalMimic.from_simple_sets(
            SimpleIntervalMimic(0.123456, 2.0), SimpleIntervalMimic(3.0, 4.0)
        )
    ).text()
    assert text == "[0.1235, 2] ∪ [3, 4]"
