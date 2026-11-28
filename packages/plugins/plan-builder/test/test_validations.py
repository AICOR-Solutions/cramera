"""
Validating a plan in a process of its own, and the gate a run on the robot passes only
with the plan whose validation passed last.
"""

from __future__ import annotations

import json
from dataclasses import replace
from importlib.machinery import ModuleSpec

import pytest

from cramera_plan_builder.bridge_processes import ProcessFile
from cramera_plan_builder.exceptions import ValidationFailed
from cramera_plan_builder.validations import PlanValidations, ValidationGate
from cramera_plan_builder.workspace import CramModules
from cramera_protocol.plan_builder import DemoDocument
from cramera_protocol.validation import (
    StepValidation,
    StepVerdict,
    ValidatedGrounding,
    ValidationOrder,
    ValidationReport,
)

from .dataset.given_workspace import DATASET

INTERPRETER = DATASET / "validating_interpreter.py"
"""
Writes a report in which every step holds.
"""

# %% fixtures


def installed() -> CramModules:
    """
    :return: Modules of which every one is installed.
    """
    return CramModules(
        finder=lambda name: ModuleSpec(name, loader=None, origin=f"{name}.py")
    )


def report_of(verdict: StepVerdict) -> ValidationReport:
    """
    :return: A report of one step with the verdict.
    """
    return ValidationReport(steps=[StepValidation(step="step_1", verdict=verdict)])


# %% validating


def test_the_report_the_validator_writes_is_answered(plan):
    validations = PlanValidations(interpreter=str(INTERPRETER), modules=installed())

    report = validations.validate(ValidationOrder(demo=DemoDocument(plan=plan)))

    assert {step.verdict for step in report.steps} == {StepVerdict.VALID}


def test_a_validator_ending_without_a_report_fails_the_validation(plan):
    validations = PlanValidations(interpreter="false", modules=installed())

    with pytest.raises(ValidationFailed):
        validations.validate(ValidationOrder(demo=DemoDocument(plan=plan)))


def test_the_next_validator_expects_the_order_validated_last(plan):
    validations = PlanValidations(interpreter=str(INTERPRETER), modules=installed())
    order = ValidationOrder(demo=DemoDocument(plan=plan))

    validations.validate(order)

    expected = validations.next_process.waiting.file(ProcessFile.EXPECTED)
    assert ValidationOrder.from_json(json.loads(expected.read_text("utf-8"))) == order
    validations.close()


# %% gate


def test_the_gate_admits_only_the_plan_that_passed_last(plan):
    gate = ValidationGate()
    gate.record(plan, report_of(StepVerdict.VALID))

    assert gate.admits(plan)
    assert not gate.admits(replace(plan, task="something else"))


def test_a_failed_validation_closes_the_gate(plan):
    gate = ValidationGate()
    gate.record(plan, report_of(StepVerdict.VALID))
    gate.record(plan, report_of(StepVerdict.FAILED))

    assert not gate.admits(plan)


def test_a_run_closes_the_gate(plan):
    gate = ValidationGate()
    gate.record(plan, report_of(StepVerdict.VALID))
    gate.close()

    assert not gate.admits(plan)


def test_a_run_refused_before_anything_moved_keeps_the_validation(plan):
    gate = ValidationGate()
    gate.record(plan, report_of(StepVerdict.VALID))
    refused = []
    gate.close(kept_if=lambda: bool(refused))

    assert not gate.admits(plan)
    refused.append(True)
    assert gate.admits(plan)
    assert not gate.admits(replace(plan, task="something else"))


def test_the_validation_kept_passes_on_to_the_next_run_only_if_that_is_refused(plan):
    gate = ValidationGate()
    gate.record(plan, report_of(StepVerdict.VALID))
    gate.close(kept_if=lambda: True)
    gate.close(kept_if=lambda: False)

    assert not gate.admits(plan)


def test_a_validation_after_the_refused_run_replaces_the_kept_one(plan):
    gate = ValidationGate()
    gate.record(plan, report_of(StepVerdict.VALID))
    gate.close(kept_if=lambda: True)
    gate.record(plan, report_of(StepVerdict.FAILED))

    assert not gate.admits(plan)


# %% the grounding a passed validation passes on


def grounded(plan) -> ValidationReport:
    """
    :return: A passed report of the plan passing its grounding on.
    """
    return replace(
        report_of(StepVerdict.VALID),
        grounding=ValidatedGrounding(
            demo=ValidatedGrounding.fingerprint(DemoDocument(plan=plan))
        ),
    )


def test_the_gate_keeps_the_grounding_of_the_plan_that_passed_last(plan):
    gate = ValidationGate()
    report = grounded(plan)
    gate.record(plan, report)

    assert gate.grounding_for(plan) == report.grounding
    assert gate.grounding_for(replace(plan, task="something else")) is None


def test_a_failed_validation_leaves_no_grounding(plan):
    gate = ValidationGate()
    gate.record(plan, grounded(plan))
    gate.record(plan, report_of(StepVerdict.FAILED))

    assert gate.grounding_for(plan) is None


def test_a_run_on_the_robot_drops_the_grounding_even_once_refused(plan):
    gate = ValidationGate()
    gate.record(plan, grounded(plan))
    gate.close(kept_if=lambda: True)

    assert gate.admits(plan)
    assert gate.grounding_for(plan) is None
