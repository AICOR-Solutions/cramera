"""
The answer of the grounding and check service: whatever generated a plan (the goal
page, a goal planner, later other generators) gets machine-readable diagnostics back,
each with a stable code, a severity, the step it concerns and a sentence for people,
so it can change the plan and ask again.

The diagnostics are read from the plan builder's validation report; the validation
itself, and the gate it opens for a run, stay as they are.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import List, Optional, Self

from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.plan_builder import PlanDocument, PlanStep
from cramera_protocol.validation import (
    StepFailureReason,
    StepValidation,
    StepVerdict,
    ValidationReport,
)

# %% codes


class DiagnosticSeverity(StrEnum):
    """
    How much a diagnostic matters.
    """

    ERROR = "error"
    """
    The plan does not pass until it is changed.
    """

    WARNING = "warning"
    """
    The plan passes, but on something the run checks again.
    """

    INFO = "info"
    """
    Nothing to change for this finding itself.
    """


class DiagnosticCode(StrEnum):
    """
    The stable codes of diagnostics; a generator may act on a code, so a code keeps
    its meaning once released, and new findings get new codes.
    """

    PLAN_REFUSED = "plan.refused"
    """
    The plan builder refused the plan before trying any step: it is incomplete, or
    names a robot, object or action the catalog does not offer.
    """

    STEP_SKILL_NOT_OFFERED = "step.skill_not_offered"
    """
    The step names a skill the robot profile does not offer.
    """

    STEP_UNREACHABLE = "step.unreachable"
    """
    The robot cannot reach where the step asks it to.
    """

    STEP_COLLISION = "step.collision"
    """
    The step's motion would bring the robot into collision.
    """

    STEP_NOT_PERCEIVED = "step.not_perceived"
    """
    No object matching the detection was seen, or assumed, in its region.
    """

    STEP_AMBIGUOUS = "step.ambiguous"
    """
    Several objects match the detection and nothing tells them apart.
    """

    STEP_SAFETY_LIMIT = "step.safety_limit"
    """
    The step's motion would break a safety limit of the robot profile.
    """

    STEP_UNSUCCESSFUL = "step.unsuccessful"
    """
    The step failed for another reason, which the diagnostic's detail names.
    """

    STEP_ASSUMED = "step.assumed"
    """
    The step succeeded on objects taken from the twin, which the run perceives again.
    """

    STEP_UNCHECKED = "step.unchecked"
    """
    The step was not tried, since a step before it failed.
    """

    @classmethod
    def of_failure(cls, reason: StepFailureReason) -> Self:
        """
        :param reason: Why a step failed its validation.
        :return: The code of that failure.
        """
        return cls(f"step.{reason.value}")

    def severity(self) -> DiagnosticSeverity:
        """
        :return: How much a diagnostic of this code matters.
        """
        if self is DiagnosticCode.STEP_ASSUMED:
            return DiagnosticSeverity.WARNING
        if self is DiagnosticCode.STEP_UNCHECKED:
            return DiagnosticSeverity.INFO
        return DiagnosticSeverity.ERROR

    def sentence(self) -> str:
        """
        :return: What a diagnostic of this code says about its step, for people.
        """
        match self:
            case DiagnosticCode.STEP_SKILL_NOT_OFFERED:
                return "uses a skill the robot profile does not offer."
            case DiagnosticCode.STEP_UNREACHABLE:
                return "asks the robot to reach where it cannot."
            case DiagnosticCode.STEP_COLLISION:
                return "would bring the robot into collision."
            case DiagnosticCode.STEP_NOT_PERCEIVED:
                return "finds no matching object in its region."
            case DiagnosticCode.STEP_AMBIGUOUS:
                return "finds several matching objects and nothing tells them apart."
            case DiagnosticCode.STEP_SAFETY_LIMIT:
                return "would break a safety limit of the robot profile."
            case DiagnosticCode.STEP_ASSUMED:
                return (
                    "holds on objects taken from the twin; the run perceives them "
                    "again."
                )
            case DiagnosticCode.STEP_UNCHECKED:
                return "was not tried, since a step before it failed."
            case _:
                return "did not succeed."


# %% diagnostics


class DiagnosticKey(StrEnum):
    """
    The keys of one diagnostic.
    """

    CODE = "code"
    """
    The diagnostic's stable code.
    """

    SEVERITY = "severity"
    """
    How much it matters.
    """

    MESSAGE = "message"
    """
    What it says, for people.
    """

    STEP_INDEX = "stepIndex"
    """
    The position of the step it concerns among the performing robot's steps, from 0.
    """

    STEP = "step"
    """
    The identity of the step it concerns.
    """

    DETAIL = "detail"
    """
    The planner's own account, for developers.
    """


@dataclass(kw_only=True)
class Diagnostic(JsonDocument):
    """
    One finding about a plan.
    """

    code: DiagnosticCode = document_field(DiagnosticKey.CODE)
    """
    The stable code.
    """

    severity: DiagnosticSeverity = document_field(DiagnosticKey.SEVERITY)
    """
    How much it matters.
    """

    message: str = document_field(DiagnosticKey.MESSAGE)
    """
    What it says, for people.
    """

    step_index: Optional[int] = document_field(DiagnosticKey.STEP_INDEX, default=None)
    """
    The position of the step it concerns among the performing robot's steps, from 0;
    None for a finding about the whole plan.
    """

    step: Optional[str] = document_field(DiagnosticKey.STEP, default=None)
    """
    The identity of the step it concerns, or None.
    """

    detail: str = document_field(DiagnosticKey.DETAIL, default="")
    """
    The planner's own account, for developers; empty when it gave none.
    """

    @classmethod
    def of_step(
        cls, index: int, step: Optional[PlanStep], validation: StepValidation
    ) -> Optional[Self]:
        """
        :param index: The step's position among the performing robot's steps.
        :param step: The step, or None when the plan has no step of that identity.
        :param validation: How it fared.
        :return: The finding about it, or None for a step that simply held.
        """
        match validation.verdict:
            case StepVerdict.VALID:
                return None
            case StepVerdict.ASSUMED:
                code = DiagnosticCode.STEP_ASSUMED
            case StepVerdict.UNCHECKED:
                code = DiagnosticCode.STEP_UNCHECKED
            case _:
                code = DiagnosticCode.of_failure(
                    validation.reason or StepFailureReason.UNSUCCESSFUL
                )
        name = validation.step if step is None else (step.skill or step.action)
        return cls(
            code=code,
            severity=code.severity(),
            message=f"Step {index + 1} ({name}) {code.sentence()}",
            step_index=index,
            step=validation.step,
            detail=validation.detail,
        )


class PlanDiagnosticsKey(StrEnum):
    """
    The keys of the diagnostics of a plan.
    """

    PASSED = "passed"
    """
    Whether the plan passed its check.
    """

    DIAGNOSTICS = "diagnostics"
    """
    The findings, in the order of the steps.
    """


@dataclass(kw_only=True)
class PlanDiagnostics(JsonDocument):
    """
    The answer of a plan's check.
    """

    passed: bool = document_field(PlanDiagnosticsKey.PASSED)
    """
    Whether the plan passed: no finding is an error.
    """

    diagnostics: List[Diagnostic] = document_field(
        PlanDiagnosticsKey.DIAGNOSTICS, default_factory=list
    )
    """
    The findings, in the order of the steps.
    """

    @classmethod
    def of_report(cls, plan: PlanDocument, report: ValidationReport) -> Self:
        """
        :param plan: The plan as it was validated.
        :param report: How each step of its performing robot fared.
        :return: A finding for every step that did not simply hold.
        """
        robot = plan.performing_robot()
        steps = {} if robot is None else {step.identifier: step for step in robot.steps}
        found = [
            Diagnostic.of_step(index, steps.get(validation.step), validation)
            for index, validation in enumerate(report.steps)
        ]
        return cls(
            passed=report.passed,
            diagnostics=[diagnostic for diagnostic in found if diagnostic is not None],
        )

    @classmethod
    def of_refusal(cls, message: str) -> Self:
        """
        :param message: Why the plan builder refused the plan before trying a step.
        :return: The one finding that it was refused.
        """
        return cls(
            passed=False,
            diagnostics=[
                Diagnostic(
                    code=DiagnosticCode.PLAN_REFUSED,
                    severity=DiagnosticCode.PLAN_REFUSED.severity(),
                    message=message,
                )
            ],
        )
