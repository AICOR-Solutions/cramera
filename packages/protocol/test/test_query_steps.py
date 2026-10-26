"""
The documents of the queries a running process asks, and the requests stepping through
them.
"""

from __future__ import annotations

import pytest

from cramera_protocol.query_steps import (
    HeldStep,
    QuerySteps,
    QueryStepsKey,
    StepAdvance,
    StepMoment,
    StepPhase,
    SteppingRequest,
    VariableRole,
)
from cramera_protocol.questions import Verbalization
from cramera_protocol.resolutions import KnowledgeSource, PerceptionReasoning

# %% round trips


@pytest.mark.parametrize(
    "document_class, relative_path",
    [
        (QuerySteps, "live/query_steps.json"),
        (StepAdvance, "live/step_advance.json"),
        (SteppingRequest, "live/stepping_request.json"),
    ],
)
def test_query_step_documents_round_trip(read_json, document_class, relative_path):
    document = document_class.from_json(read_json(relative_path))
    assert document_class.from_json(document.to_json()) == document


# %% steps


def test_the_steps_read_the_step_the_process_is_held_at(read_json):
    data = read_json("live/query_steps.json")
    steps = QuerySteps.from_json(data)
    assert steps.held == HeldStep.from_json(data[QueryStepsKey.HELD])


def test_a_step_reads_its_question_variables_and_reasoning(read_json):
    data = read_json("live/query_steps.json")
    step = QuerySteps.from_json(data).steps[0]
    assert step.question == Verbalization.from_json(data["steps"][0]["question"])
    assert [variable.role for variable in step.variables] == [
        VariableRole.SOUGHT,
        VariableRole.GIVEN,
        VariableRole.RANGES_OVER,
    ]
    assert isinstance(step.reasoning, PerceptionReasoning)
    assert step.backend.source is KnowledgeSource.PERCEPTION


def test_a_nested_step_names_the_step_that_asked_it(read_json):
    steps = QuerySteps.from_json(read_json("live/query_steps.json")).steps
    assert steps[1].asker == steps[0].number
    assert steps[1].phase is StepPhase.EXECUTION


def test_a_step_without_a_question_or_code_reads_them_as_absent(read_json):
    step = QuerySteps.from_json(read_json("live/query_steps.json")).steps[1]
    assert (step.question, step.code, step.caller, step.reasoning) == (
        None,
        None,
        None,
        None,
    )


def test_steps_published_by_nothing_hold_nothing():
    steps = QuerySteps.from_json({})
    assert (steps.held, steps.steps, steps.stepping) == (None, [], False)


# %% requests


def test_an_advance_names_the_step_the_viewer_saw(read_json):
    advance = StepAdvance.from_json(read_json("live/step_advance.json"))
    assert advance.held == HeldStep(number=1, moment=StepMoment.ASKED)


def test_an_advance_without_a_step_lets_any_held_step_go():
    assert StepAdvance.from_json({}).held is None


def test_a_stepping_request_holds_at_nested_queries_by_default():
    assert SteppingRequest.from_json({"stepping": True}).holds_nested is True
