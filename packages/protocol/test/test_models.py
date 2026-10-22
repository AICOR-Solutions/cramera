"""
The documents of the probabilistic-models workbench.
"""

from __future__ import annotations

import pytest

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.exceptions import InvalidDocumentValue, MissingDocumentField
from cramera_protocol.models import (
    ConstraintKey,
    FigureKey,
    IntervalKey,
    ModeAnswer,
    ModelRequestKey,
    ModelVariable,
    ModelVariableKey,
    ModelUpload,
    PosteriorRequest,
    ProbabilityRequest,
    VariableKind,
    WorkbenchState,
    WorkbenchStateKey,
)

# %% state


def test_the_workbench_state_reads_symbolic_and_numeric_variables(read_json):
    data = read_json("models/workbench_state.json")
    state = WorkbenchState.from_json(data)
    symbolic, numeric = data[WorkbenchStateKey.VARIABLES]
    assert state.variables[0].kind is VariableKind.SYMBOLIC
    assert state.variables[0].values == symbolic[ModelVariableKey.VALUES]
    assert state.variables[0].low is None
    assert state.variables[1].kind is VariableKind.CONTINUOUS
    assert state.variables[1].low == numeric[ModelVariableKey.LOW]
    assert state.variables[1].high == numeric[ModelVariableKey.HIGH]
    assert WorkbenchState.from_json(state.to_json()) == state


def test_an_empty_workbench_writes_no_name():
    assert WorkbenchState(loaded=False).to_json() == {
        WorkbenchStateKey.LOADED: False,
        WorkbenchStateKey.VARIABLES: [],
    }


def test_a_variable_of_an_unknown_kind_is_refused(read_json):
    with pytest.raises(InvalidDocumentValue):
        ModelVariable.from_json(read_json("models/variable_with_unknown_kind.json"))


# %% requests


def test_a_probability_request_reads_intervals_and_values(read_json):
    data = read_json("models/probability_request.json")
    request = ProbabilityRequest.from_json(data)
    query = data[ModelRequestKey.QUERY][0]
    evidence = data[ModelRequestKey.EVIDENCE][0]
    assert request.query[0].variable == query[ConstraintKey.VARIABLE]
    assert [interval.high for interval in request.query[0].intervals] == [
        interval[IntervalKey.HIGH] for interval in query[ConstraintKey.INTERVALS]
    ]
    assert request.query[0].values == []
    assert request.evidence[0].values == evidence[ConstraintKey.VALUES]
    assert request.evidence[0].intervals == []
    assert ProbabilityRequest.from_json(request.to_json()) == request


def test_a_probability_request_without_events_asks_about_certainty():
    request = ProbabilityRequest.from_json({})
    assert request.query == []
    assert request.evidence == []


def test_a_posterior_request_needs_its_variables(read_json):
    with pytest.raises(MissingDocumentField):
        PosteriorRequest.from_json(
            read_json("models/posterior_request_without_variables.json")
        )


def test_a_model_upload_round_trips():
    upload = ModelUpload(name="circuit.json", text='{"weights": [Infinity]}')
    assert ModelUpload.from_json(upload.to_json()) == upload


# %% answers


def test_a_mode_answer_round_trips(read_json):
    data = read_json("models/mode_answer.json")
    assert ModeAnswer.from_json(data).to_json() == data


# %% figures


def test_the_figure_keys_reach_the_browser():
    assert FigureKey in BROWSER_ENUMERATIONS
