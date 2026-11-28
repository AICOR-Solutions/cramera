"""
The plan builder's check route: the grounding and check service's entry, which wraps the
existing validation and answers machine-readable diagnostics, leaving the validation
gate as it is.
"""

from __future__ import annotations

import json
from dataclasses import replace
from http import HTTPStatus

import pytest

from cramera.http.messages import HttpMethod
from cramera_plan_builder.exceptions import PlanNotValidated
from cramera_protocol.grounding import (
    DiagnosticCode,
    DiagnosticSeverity,
    PlanDiagnostics,
)
from cramera_protocol.plan_builder import PlanBuilderRoute, RunMode
from cramera_protocol.validation import ValidationRequest

from .conftest import send
from .dataset.given_workspace import DATASET
from .test_plugin import run_on_the_robot, validate, validating_plugin


@pytest.fixture
def checking(serve, output, workspace_loader):
    """
    :return: Answers requests to a plan builder of Tracy's test profile with the
        stand-in validator, which fails the step a plan's task names as unreachable.
    """
    return serve(
        validating_plugin(output, workspace_loader, DATASET / "profile" / "tracy.json")
    )


def check(answer, plan) -> PlanDiagnostics:
    """
    :return: The diagnostics the plan builder answers a check of the plan with.
    """
    checked = send(
        answer,
        HttpMethod.POST,
        PlanBuilderRoute.CHECK,
        json.dumps(ValidationRequest(plan=plan).to_json()).encode(),
    )
    assert checked.status == HTTPStatus.OK, checked.body
    return PlanDiagnostics.from_json(json.loads(checked.body))


def test_an_unreachable_placement_is_diagnosed_with_a_stable_code(checking, plan):
    steps = plan.performing_robot().steps
    [place_index] = [
        index for index, step in enumerate(steps) if step.action == "place"
    ]
    unreachable = replace(plan, task=steps[place_index].identifier)

    diagnostics = check(checking, unreachable)

    assert not diagnostics.passed
    [diagnostic] = diagnostics.diagnostics
    assert diagnostic.code == "step.unreachable"
    assert diagnostic.code is DiagnosticCode.STEP_UNREACHABLE
    assert diagnostic.severity is DiagnosticSeverity.ERROR
    assert diagnostic.step_index == place_index
    assert diagnostic.step == steps[place_index].identifier


def test_a_plan_whose_steps_all_hold_passes_without_findings(checking, plan):
    diagnostics = check(checking, plan)

    assert diagnostics.passed
    assert diagnostics.diagnostics == []


def test_a_passed_check_does_not_admit_the_plan_to_a_robot_run(checking, plan):
    assert check(checking, plan).passed

    assert run_on_the_robot(checking, plan) == PlanNotValidated(RunMode.ROBOT).status()


def test_a_failed_check_leaves_a_passed_validation_admitted(checking, plan):
    validate(checking, plan)
    failing = replace(plan, task=plan.performing_robot().steps[0].identifier)

    assert not check(checking, failing).passed

    assert run_on_the_robot(checking, plan) != PlanNotValidated(RunMode.ROBOT).status()


def test_a_plan_the_catalog_refuses_is_diagnosed_instead_of_refused(checking, plan):
    plan.objects[0].model = "anvil.stl"

    diagnostics = check(checking, plan)

    assert not diagnostics.passed
    [refused] = diagnostics.diagnostics
    assert refused.code is DiagnosticCode.PLAN_REFUSED
    assert refused.step_index is None
    assert "anvil.stl" in refused.message
