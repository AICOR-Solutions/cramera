"""
Grounding a plan before it runs: the performing robot's steps are tried one after
another in a copy of the plan's world by coraplex's
:class:`~coraplex.plans.validation.PlanValidation`, so nothing real moves. A step that
leaves its arm open is given the arm that reaches, and a detection is answered from
where the robot's camera sees its region now, else from the twin.

Validating a plan reports how every step fared; running it grounds it the same way
first, so it runs with the arms its validation chose.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from typing_extensions import Any, Dict, List, Optional

from coraplex.perception import PerceptionInterface
from coraplex.plans.validation import (
    FailureCause,
    PlanValidation,
    StepCheck,
    ValidationVerdict,
)
from cramera_bridge.geometry import NumericPose
from cramera_bridge.names import ENUM_NAMES
from cramera_bridge.performing import TaskContext
from cramera_bridge.plans.actions import DiscoveredActions
from cramera_bridge.plans.arms import Arms, RobotArms
from cramera_bridge.plans.detected_objects import DetectedObjects
from cramera_bridge.plans.site import RobotSite
from cramera_bridge.plans.steps import StepActions, StepArguments
from cramera_protocol.detection import DetectedObjectReference
from cramera_protocol.plan_builder import PlanStep
from cramera_protocol.validation import (
    StepFailureReason,
    StepValidation,
    StepVerdict,
)
from semantic_digital_twin.world_description.world_entity import Body

# %% one step


@dataclass(frozen=True)
class GroundedStep:
    """
    A step of the performing robot as it was grounded.
    """

    step: PlanStep
    """
    The step as the plan names it.
    """

    check: Optional[StepCheck] = None
    """
    How it fared in the copy of the world, or None when a step before it failed.
    """

    arm: Optional[Arms] = None
    """
    The arm a step leaving its arm open was given; None for any other step.
    """

    arm_field: Optional[str] = None
    """
    The identifier of the field whose arm the step leaves open.
    """

    resolved_destinations: Dict[str, Any] = field(default_factory=dict)
    """
    The value of each field whose destination was only known once the plan was grounded,
    as the pose it resolved to.
    """

    expected_positions: Dict[str, List[float]] = field(default_factory=dict)
    """
    Where the objects the step expects in place lay when it was grounded, by their
    identity, in the world's coordinates.
    """

    @property
    def succeeded(self) -> bool:
        """
        Whether the step succeeded, on perceived or on assumed objects.
        """
        return self.check is not None and self.check.verdict is not (
            ValidationVerdict.FAILED
        )

    def resolved_step(self) -> PlanStep:
        """
        :return: The step naming the arm it was given in place of the open one, and
            the poses its destinations resolved to in place of those only known once
            the plan was grounded; the step itself when it leaves neither open.
        """
        values = {**self.step.values, **self.resolved_destinations}
        if self.arm is not None:
            values[self.arm_field] = ENUM_NAMES.member_identifier(Arms, self.arm)
        return replace(self.step, values=values)

    def to_step_validation(self) -> StepValidation:
        """
        :return: How the step fared, in the protocol's words.
        """
        arm = None if self.arm is None else ENUM_NAMES.member_identifier(Arms, self.arm)
        if self.check is None:
            return StepValidation(
                step=self.step.identifier, verdict=StepVerdict.UNCHECKED
            )
        if self.check.verdict is ValidationVerdict.ASSUMED:
            return StepValidation(
                step=self.step.identifier, verdict=StepVerdict.ASSUMED, arm=arm
            )
        if self.check.verdict is ValidationVerdict.VALID:
            return StepValidation(
                step=self.step.identifier, verdict=StepVerdict.VALID, arm=arm
            )
        failure = (self.check.candidate_failures or [self.check.failure])[0]
        return StepValidation(
            step=self.step.identifier,
            verdict=StepVerdict.FAILED,
            reason=self.translate_cause(self.check.cause),
            detail=str(failure),
        )

    @staticmethod
    def translate_cause(cause: FailureCause) -> StepFailureReason:
        """
        :param cause: Why coraplex says a step failed.
        :return: The protocol's name of it.
        """
        match cause:
            case FailureCause.UNREACHABLE:
                return StepFailureReason.UNREACHABLE
            case FailureCause.COLLISION:
                return StepFailureReason.COLLISION
            case FailureCause.NOT_PERCEIVED:
                return StepFailureReason.NOT_PERCEIVED
            case FailureCause.AMBIGUOUS:
                return StepFailureReason.AMBIGUOUS
        return StepFailureReason.UNSUCCESSFUL


# %% the plan


@dataclass
class PlanGrounding:
    """
    Grounds the steps of the performing robot one after another in a copy of the plan's
    world, stopping at the first step that fails.
    """

    context: TaskContext
    """
    The plan's world and its performing robot, which are never modified.
    """

    bodies: Dict[str, Body]
    """
    The plan's objects by their identity, in :attr:`context`'s world.
    """

    actions: DiscoveredActions
    """
    The workspace's actions, which steps name.
    """

    perception: PerceptionInterface
    """
    The robot's perception, asked where its camera sees a detection's region now.
    """

    site: RobotSite = field(default_factory=RobotSite)
    """
    Where the plan stands the robot, and the robot profile's zones.
    """

    validation: PlanValidation = field(init=False)
    """
    Tries the steps in its copy of the world.
    """

    copied_context: TaskContext = field(init=False)
    """
    The copy of the world and its performing robot, which the steps are built in.
    """

    copied_bodies: Dict[str, Body] = field(init=False)
    """
    The plan's objects in the copy, and once a detection step was grounded, the object
    it found by the reference later steps name it with.
    """

    def __post_init__(self) -> None:
        self.validation = PlanValidation(
            world=self.context.world,
            extensions=self.context.context_extensions(),
            perception=self.perception,
            collision_avoidance=self.context.collision_avoidance,
        )
        copy = self.validation.copied_world
        self.copied_context = TaskContext(
            world=copy, robot=copy.rebind_world_entities(self.context.robot)
        )
        self.copied_bodies = {
            identifier: copy.rebind_world_entities(body)
            for identifier, body in self.bodies.items()
        }

    def ground(self, steps: List[PlanStep]) -> List[GroundedStep]:
        """
        :param steps: The steps of the performing robot, in order.
        :return: How each was grounded; those after the first that failed are not
            tried.
        """
        grounded = []
        for step in steps:
            if grounded and not grounded[-1].succeeded:
                grounded.append(GroundedStep(step=step))
                continue
            grounded.append(self.ground_step(step))
        return grounded

    def ground_step(self, step: PlanStep) -> GroundedStep:
        """
        :param step: The next step of the performing robot.
        :return: How it was grounded where the steps before it left the copy.
        """
        if self.actions.named(step.action).looks_for_objects():
            return self.ground_detection(step)
        arguments = StepArguments(
            context=self.copied_context,
            bodies=self.copied_bodies,
            action=self.actions.named(step.action),
            step=step,
            site=self.site,
        )
        expected = {
            identifier: list(
                NumericPose.of_entity(
                    self.copied_context.world, self.copied_bodies[identifier]
                ).position
            )
            for identifier in arguments.objects_expected_in_place()
            if identifier in self.copied_bodies
        }
        open_field = arguments.find_open_arm_field()
        placement_failure = arguments.placement_failure()
        if placement_failure is not None:
            return GroundedStep(
                step=step,
                check=StepCheck(
                    verdict=ValidationVerdict.FAILED, failure=placement_failure
                ),
            )
        resolved = arguments.resolved_destinations()
        check = self.validation.check(
            StepActions(
                self.copied_context, self.copied_bodies, self.actions, site=self.site
            ).action(replace(step, values={**step.values, **resolved}))
        )
        if open_field is None or check.grounded_action is None:
            return GroundedStep(
                step=step,
                check=check,
                resolved_destinations=resolved,
                expected_positions=expected,
            )
        return GroundedStep(
            step=step,
            check=check,
            arm=RobotArms(self.copied_context.robot).find_side(
                vars(check.grounded_action)[arguments.action.field_name(open_field)]
            ),
            arm_field=open_field,
            resolved_destinations=resolved,
            expected_positions=expected,
        )

    def ground_detection(self, step: PlanStep) -> GroundedStep:
        """
        :param step: A step looking for an object.
        :return: How it was grounded; the object it found is what later steps name by
            its reference.
        """
        query = DetectedObjects(
            self.copied_context, self.copied_bodies, self.actions, site=self.site
        ).query(step)
        check = self.validation.check_detection(query)
        if check.found:
            self.copied_bodies[DetectedObjectReference(step.identifier).text] = (
                check.found[0]
            )
        return GroundedStep(step=step, check=check)
