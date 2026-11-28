"""
The diagnostics of the grounding and check service: a validation's report as
machine-readable findings with stable codes, so whatever generated a plan can iterate.
"""

from __future__ import annotations

from cramera_protocol.browser import BROWSER_ENUMERATIONS
from cramera_protocol.grounding import (
    DiagnosticCode,
    DiagnosticKey,
    DiagnosticSeverity,
    PlanDiagnostics,
    PlanDiagnosticsKey,
)
from cramera_protocol.plan_builder import PlanDocument
from cramera_protocol.validation import (
    StepFailureReason,
    StepValidation,
    StepVerdict,
    ValidationReport,
)


def two_step_plan() -> PlanDocument:
    return PlanDocument.from_json(
        {
            "name": "tower",
            "robots": [
                {
                    "id": "robot_1",
                    "model": "tracy",
                    "label": "Tracy",
                    "pose": [0, 0, 0, 0, 0, 0, 1],
                    "steps": [
                        {
                            "id": "step_1",
                            "skill": "pick",
                            "action": "pick_up",
                            "values": {"grasp": "red_cube"},
                        },
                        {
                            "id": "step_2",
                            "skill": "place",
                            "action": "place",
                            "values": {"object_designator": "red_cube"},
                        },
                        {"id": "step_3", "skill": "park_arms", "action": "park_arms"},
                    ],
                }
            ],
        }
    )


def test_an_unreachable_placement_is_an_error_with_a_stable_code_at_its_step():
    report = ValidationReport(
        steps=[
            StepValidation(step="step_1", verdict=StepVerdict.VALID),
            StepValidation(
                step="step_2",
                verdict=StepVerdict.FAILED,
                reason=StepFailureReason.UNREACHABLE,
                detail="IK found no solution",
            ),
            StepValidation(step="step_3", verdict=StepVerdict.UNCHECKED),
        ]
    )
    diagnostics = PlanDiagnostics.of_report(two_step_plan(), report)
    [unreachable, unchecked] = diagnostics.diagnostics
    assert not diagnostics.passed
    assert unreachable.code == DiagnosticCode.STEP_UNREACHABLE == "step.unreachable"
    assert unreachable.severity is DiagnosticSeverity.ERROR
    assert (unreachable.step_index, unreachable.step) == (1, "step_2")
    assert unreachable.detail == "IK found no solution"
    assert "Step 2 (place)" in unreachable.message
    assert unchecked.code == DiagnosticCode.STEP_UNCHECKED
    assert unchecked.severity is DiagnosticSeverity.INFO


def test_every_failure_reason_has_a_code_of_its_own():
    codes = {DiagnosticCode.of_failure(reason) for reason in StepFailureReason}
    assert len(codes) == len(StepFailureReason)
    assert all(code.value.startswith("step.") for code in codes)


def test_a_step_on_assumed_objects_is_a_warning_and_the_plan_still_passes():
    report = ValidationReport(
        steps=[
            StepValidation(step="step_1", verdict=StepVerdict.ASSUMED),
            StepValidation(step="step_2", verdict=StepVerdict.VALID),
            StepValidation(step="step_3", verdict=StepVerdict.VALID),
        ]
    )
    diagnostics = PlanDiagnostics.of_report(two_step_plan(), report)
    assert diagnostics.passed
    [assumed] = diagnostics.diagnostics
    assert (assumed.code, assumed.severity) == (
        DiagnosticCode.STEP_ASSUMED,
        DiagnosticSeverity.WARNING,
    )


def test_a_refused_plan_is_one_error_without_a_step():
    diagnostics = PlanDiagnostics.of_refusal("The plan names no robot.")
    [refused] = diagnostics.diagnostics
    assert not diagnostics.passed
    assert refused.code == DiagnosticCode.PLAN_REFUSED
    assert refused.step_index is None
    assert refused.message == "The plan names no robot."


def test_diagnostics_read_back_from_their_json():
    report = ValidationReport(
        steps=[
            StepValidation(
                step="step_1",
                verdict=StepVerdict.FAILED,
                reason=StepFailureReason.COLLISION,
            )
        ]
    )
    diagnostics = PlanDiagnostics.of_report(two_step_plan(), report)
    data = diagnostics.to_json()
    assert data[PlanDiagnosticsKey.PASSED] is False
    assert data[PlanDiagnosticsKey.DIAGNOSTICS][0][DiagnosticKey.CODE] == (
        "step.collision"
    )
    assert PlanDiagnostics.from_json(data) == diagnostics


def test_the_browser_reads_the_names_of_diagnostics():
    assert {
        DiagnosticCode,
        DiagnosticSeverity,
        DiagnosticKey,
        PlanDiagnosticsKey,
    } <= set(BROWSER_ENUMERATIONS)
