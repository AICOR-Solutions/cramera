"""
The circuit workbench over the installed circuit libraries, with a real circuit:

``x ~ Uniform(0, 1)`` times ``color ~ {red: 0.7, blue: 0.3}``. Skipped where the
libraries are missing; ``test_circuit_workbench_mimic`` tests the same behaviour against
stand-ins everywhere.
"""

from __future__ import annotations

import importlib
import json
from types import ModuleType

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
    ModelsRoute,
    ModelUpload,
    ModeRequest,
    PosteriorAnswer,
    PosteriorRequest,
    ProbabilityAnswer,
    ProbabilityRequest,
    VariableKind,
    WorkbenchState,
)

from .dataset.requests import answer_json, local_get, local_post


@pytest.fixture
def circuit(circuit_workbench_module) -> ModuleType:
    """
    :return: The module building the dataset's circuit; imported here because it
        imports the circuit libraries, which the fixture it depends on has found.
    """
    return importlib.import_module(f"{__package__}.dataset.uniform_and_color_circuit")


@pytest.fixture
def upload(circuit) -> ModelUpload:
    """
    :return: The dataset's circuit file.
    """
    return circuit.uniform_and_color()


@pytest.fixture
def workbench(circuit_workbench_module, upload):
    """
    :return: A circuit workbench with the dataset's circuit loaded.
    """
    workbench = circuit_workbench_module.CircuitWorkbench()
    workbench.load(upload)
    return workbench


def asked(question, name, document_class):
    """
    :param question: Reads a request body of the dataset.
    :param name: The body's file name.
    :param document_class: The request document.
    :return: The request.
    """
    return document_class.from_json(json.loads(question(name)))


# %% state


def test_an_empty_workbench_has_no_model(circuit_workbench_module):
    state = circuit_workbench_module.CircuitWorkbench().state()
    assert state == WorkbenchState(loaded=False)


def test_loading_describes_the_variables(workbench, circuit, upload):
    state = workbench.state()
    assert state.name == upload.name
    variables = {variable.name: variable for variable in state.variables}
    assert variables["color"].kind == VariableKind.SYMBOLIC
    assert sorted(variables["color"].values) == sorted(circuit.COLOR_PROBABILITIES)
    assert variables["x"].kind == VariableKind.CONTINUOUS
    assert (variables["x"].low, variables["x"].high) == (0.0, 1.0)


@pytest.mark.parametrize(
    "file, error",
    [
        ("questions/not_json.txt", InvalidJson),
        ("object_without_circuit.json", NotACircuit),
        ("list_instead_of_circuit.json", NotACircuit),
    ],
)
def test_a_file_without_a_circuit_is_refused(
    circuit_workbench_module, upload_of, file, error
):
    with pytest.raises(error):
        circuit_workbench_module.CircuitWorkbench().load(upload_of(file))


def test_questions_without_a_model_are_refused(circuit_workbench_module):
    with pytest.raises(NoModelLoaded):
        circuit_workbench_module.CircuitWorkbench().mode(ModeRequest())


# %% probability


def test_an_interval_query_given_independent_evidence(workbench, question):
    answer = workbench.probability(
        asked(question, "probability_of_low_x_given_red.json", ProbabilityRequest)
    )
    assert answer.probability == pytest.approx(0.25)


def test_two_rows_on_one_variable_are_united(workbench, question):
    answer = workbench.probability(
        asked(question, "probability_of_two_x_rows.json", ProbabilityRequest)
    )
    assert answer.probability == pytest.approx(0.2)


def test_a_row_without_intervals_is_the_whole_domain(workbench, question):
    answer = workbench.probability(
        asked(question, "probability_of_any_x.json", ProbabilityRequest)
    )
    assert answer.probability == pytest.approx(1.0)


def test_an_unknown_variable_is_refused(workbench, question):
    with pytest.raises(UnknownVariable) as refused:
        workbench.probability(
            asked(question, "probability_of_unknown_variable.json", ProbabilityRequest)
        )
    assert refused.value.name == "temperature"


# %% posterior and mode


def test_each_asked_variable_gets_a_figure(workbench, question):
    request = asked(question, "posterior_of_x_and_color.json", PosteriorRequest)
    answer = workbench.posterior(request)
    assert sorted(answer.figures) == sorted(request.variables)
    assert all(figure[FigureKey.DATA] for figure in answer.figures.values())


def test_a_posterior_given_impossible_evidence_is_refused(workbench, question):
    with pytest.raises(ImpossibleEvidence):
        workbench.posterior(
            asked(
                question, "posterior_given_impossible_evidence.json", PosteriorRequest
            )
        )


def test_the_unconditioned_mode_picks_the_likelier_color(workbench, question, circuit):
    answer = workbench.mode(asked(question, "mode_without_evidence.json", ModeRequest))
    likelier = max(circuit.COLOR_PROBABILITIES, key=circuit.COLOR_PROBABILITIES.get)
    assert [mode["color"] for mode in answer.modes] == [likelier]
    assert answer.likelihood == pytest.approx(circuit.COLOR_PROBABILITIES[likelier])


def test_the_mode_follows_the_evidence(workbench, question):
    answer = workbench.mode(asked(question, "mode_given_blue.json", ModeRequest))
    assert [mode["color"] for mode in answer.modes] == ["blue"]


def test_a_mode_given_impossible_evidence_is_refused(workbench, question):
    with pytest.raises(ImpossibleEvidence):
        workbench.mode(
            asked(question, "mode_given_impossible_evidence.json", ModeRequest)
        )


# %% over HTTP


def test_the_panel_flow_over_http(
    circuit_workbench_module, answerer_of, upload, question
):
    answerer = answerer_of(circuit_workbench_module.CircuitWorkbench())
    body = json.dumps(upload.to_json()).encode()
    loaded = answerer.answer(local_post(ModelsRoute.LOAD, body))
    assert WorkbenchState.from_json(answer_json(loaded)).loaded
    state = answerer.answer(local_get(ModelsRoute.STATE))
    assert WorkbenchState.from_json(answer_json(state)).name == upload.name
    probability = answerer.answer(
        local_post(ModelsRoute.PROBABILITY, question("probability_of_any_x.json"))
    )
    assert ProbabilityAnswer.from_json(answer_json(probability)).probability == (
        pytest.approx(1.0)
    )
    posterior = answerer.answer(
        local_post(ModelsRoute.POSTERIOR, question("posterior_of_x_and_color.json"))
    )
    assert sorted(PosteriorAnswer.from_json(answer_json(posterior)).figures) == [
        "color",
        "x",
    ]
    impossible = answerer.answer(
        local_post(ModelsRoute.MODE, question("mode_given_impossible_evidence.json"))
    )
    assert impossible.status == ImpossibleEvidence().status()


def test_a_circuit_file_with_infinity_loads_as_text(upload, circuit_workbench_module):
    assert "Infinity" in upload.text
    state = circuit_workbench_module.CircuitWorkbench().load(upload)
    assert state.loaded
