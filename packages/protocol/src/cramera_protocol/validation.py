"""
Validating a plan before it runs on the robot: every step of the performing robot is
tried in a copy of the twin without moving anything, and the report says of each step
whether it holds, holds on objects only assumed, or fails and why.

A plan runs on the robot only once its latest version passed; a plan edit or a change of
the scene invalidates the report.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from typing_extensions import Dict, List, Optional

from cramera_protocol.detection import InlineImage
from cramera_protocol.document import JsonDocument, document_field
from cramera_protocol.plan_builder import (
    DemoDocument,
    PlanDocument,
    PlannedObject,
    PlanStep,
)

# %% verdicts


class StepVerdict(StrEnum):
    """
    How a step fared when the plan was validated.
    """

    VALID = "valid"
    """
    The step succeeded in the copy of the twin.
    """

    ASSUMED = "assumed"
    """
    The step succeeded on objects taken from the twin, since the camera does not see
    them now; they are perceived again when the plan runs.
    """

    FAILED = "failed"
    """
    The step did not succeed.
    """

    UNCHECKED = "unchecked"
    """
    The step was not tried, since a step before it failed.
    """


class StepFailureReason(StrEnum):
    """
    Why a step failed its validation.
    """

    UNREACHABLE = "unreachable"
    """
    The robot cannot reach where the step asks it to.
    """

    COLLISION = "collision"
    """
    The step's motion would bring the robot into collision.
    """

    NOT_PERCEIVED = "not_perceived"
    """
    No object matching the detection was seen, or assumed, in its region.
    """

    AMBIGUOUS = "ambiguous"
    """
    Several objects match the detection and nothing tells them apart.
    """

    SAFETY_LIMIT = "safety_limit"
    """
    The step's motion would break a safety limit of the robot profile: an arm's tool
    would leave its workspace box, or come closer to its edge than a validated plan
    may.
    """

    SKILL_NOT_OFFERED = "skill_not_offered"
    """
    The step names a skill the robot profile does not offer.
    """

    UNSUCCESSFUL = "unsuccessful"
    """
    The step failed for another reason, which its detail names.
    """


class StepValidationKey(StrEnum):
    """
    The keys of one step's validation.
    """

    STEP = "step"
    """
    The step's identity.
    """

    VERDICT = "verdict"
    """
    How the step fared.
    """

    REASON = "reason"
    """
    Why it failed.
    """

    ARM = "arm"
    """
    The arm the step was given.
    """

    DETAIL = "detail"
    """
    What failed it, in the planner's words.
    """

    IMAGES = "images"
    """
    What a detection saw.
    """


@dataclass(kw_only=True)
class StepValidation(JsonDocument):
    """
    How one step of the performing robot fared when the plan was validated.
    """

    step: str = document_field(StepValidationKey.STEP)
    """
    The identity of the step.
    """

    verdict: StepVerdict = document_field(StepValidationKey.VERDICT)
    """
    How it fared.
    """

    reason: Optional[StepFailureReason] = document_field(
        StepValidationKey.REASON, default=None
    )
    """
    Why it failed, or None for a step that did not fail.
    """

    arm: Optional[str] = document_field(StepValidationKey.ARM, default=None)
    """
    The arm a step that leaves its arm to be chosen automatically is given, as the
    member identifier of the arm enumeration; None for any other step.
    """

    detail: str = document_field(StepValidationKey.DETAIL, default="")
    """
    The planner's own account of the failure, for developers.
    """

    images: List[InlineImage] = document_field(
        StepValidationKey.IMAGES, default_factory=list
    )
    """
    What a detection step saw; empty for any other step.
    """


# %% the grounding a validation passes on


class GroundedStepKey(StrEnum):
    """
    The keys of a step as a validation grounded it.
    """

    RESOLVED = "resolved"
    """
    The step naming the arm and the poses its grounding chose.
    """

    EXPECTED_POSITIONS = "expectedPositions"
    """
    Where the objects the step expects in place lay, by their identity.
    """


@dataclass(kw_only=True)
class GroundedStepDocument(JsonDocument):
    """
    A step of the performing robot as a passed validation grounded it.
    """

    resolved: PlanStep = document_field(GroundedStepKey.RESOLVED)
    """
    The step naming the arm it was given in place of an open one, and the poses its
    destinations resolved to.
    """

    expected_positions: Dict[str, List[float]] = document_field(
        GroundedStepKey.EXPECTED_POSITIONS, default_factory=dict
    )
    """
    Where the objects the step expects in place lay when it was grounded, by their
    identity, in the world's coordinates.
    """


class ValidatedGroundingKey(StrEnum):
    """
    The keys of the grounding a validation passes on.
    """

    DEMO = "demo"
    """
    The fingerprint of the plan and its environment that were grounded.
    """

    STEPS = "steps"
    """
    The performing robot's steps as they were grounded.
    """


@dataclass(kw_only=True)
class ValidatedGrounding(JsonDocument):
    """
    How a passed validation grounded the performing robot's steps in a copy of the
    twin, which a simulated run of the same plan in the same twin performs instead of
    grounding the plan again; a run on the real robot always grounds it afresh, since
    the real world may have moved since.
    """

    demo: str = document_field(ValidatedGroundingKey.DEMO)
    """
    The :meth:`fingerprint` of the plan and its environment that were grounded.
    """

    steps: List[GroundedStepDocument] = document_field(
        ValidatedGroundingKey.STEPS, default_factory=list
    )
    """
    The performing robot's steps as they were grounded, in their order.
    """

    @staticmethod
    def fingerprint(demo: DemoDocument) -> str:
        """
        :param demo: A plan and its environment.
        :return: A digest of its JSON, the same for the same plan in the same twin and
            environment, and different once anything of them changed.
        """
        text = json.dumps(demo.to_json(), sort_keys=True)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def describes(self, demo: DemoDocument) -> bool:
        """
        :param demo: The plan and environment of a run.
        :return: Whether this grounding was made of exactly that plan and environment.
        """
        return self.demo == self.fingerprint(demo)


# %% report


class ValidationReportKey(StrEnum):
    """
    The keys of a validation's report.
    """

    STEPS = "steps"
    """
    How each step fared.
    """

    SECONDS = "seconds"
    """
    How long the validation took.
    """

    GROUNDING = "grounding"
    """
    The grounding a simulated run of the validated plan may perform.
    """


@dataclass(kw_only=True)
class ValidationReport(JsonDocument):
    """
    How each step of the performing robot fared when the plan was validated, in the
    order of the steps.
    """

    steps: List[StepValidation] = document_field(
        ValidationReportKey.STEPS, default_factory=list
    )
    """
    How each step fared.
    """

    seconds: float = document_field(ValidationReportKey.SECONDS, default=0.0)
    """
    How long the validation took, in seconds.
    """

    grounding: Optional[ValidatedGrounding] = document_field(
        ValidationReportKey.GROUNDING, default=None
    )
    """
    The grounding of a passed validation that a simulated run of the same plan may
    perform instead of grounding it again; None when the validation failed, perceived
    objects or started from the real robot's posture. The plan builder keeps it and
    never sends it to the page.
    """

    @property
    def passed(self) -> bool:
        """
        Whether every step succeeded, on perceived or on assumed objects.
        """
        return all(
            step.verdict in (StepVerdict.VALID, StepVerdict.ASSUMED)
            for step in self.steps
        )


# %% requests


class ValidationRequestKey(StrEnum):
    """
    The keys of a request to validate a plan.
    """

    PLAN = "plan"
    """
    The plan to validate.
    """


@dataclass(kw_only=True)
class ValidationRequest(JsonDocument):
    """
    Asks the plan builder to validate a plan.
    """

    plan: PlanDocument = document_field(ValidationRequestKey.PLAN)
    """
    The plan, whose selected robot's steps are validated.
    """


class ValidationCancellationKey(StrEnum):
    """
    The keys of the answer to cancelling the validations running now.
    """

    CANCELLED = "cancelled"
    """
    Whether a validation ran and was cancelled.
    """


@dataclass(kw_only=True)
class ValidationCancellation(JsonDocument):
    """
    What cancelling the validations running now ended; the plan builder records no
    report of a cancelled validation.
    """

    cancelled: bool = document_field(ValidationCancellationKey.CANCELLED)
    """
    Whether a validation ran and was cancelled.
    """


class ValidationOrderKey(StrEnum):
    """
    The keys of what the bridge validates.
    """

    DEMO = "demo"
    """
    The plan and its environment.
    """

    SIMULATED_OBJECTS = "simulatedObjects"
    """
    The objects of the simulated scene the camera is rendered from.
    """

    READS_ROBOT_POSTURE = "readsRobotPosture"
    """
    Whether the robot starts from the joint positions the real robot reports.
    """


@dataclass(kw_only=True)
class ValidationOrder(JsonDocument):
    """
    What the bridge validates: a checked plan in its environment, and the scene the
    robot's camera sees.
    """

    demo: DemoDocument = document_field(ValidationOrderKey.DEMO)
    """
    The plan and its environment.
    """

    simulated_objects: Optional[List[PlannedObject]] = document_field(
        ValidationOrderKey.SIMULATED_OBJECTS, default=None
    )
    """
    The objects standing in a simulated scene that the robot's camera is rendered from,
    or None to ask the robot's own perception.
    """

    reads_robot_posture: bool = document_field(
        ValidationOrderKey.READS_ROBOT_POSTURE, default=False
    )
    """
    Whether the robot starts from the joint positions the real robot reports, rather
    than from the posture the plan gives it.
    """
