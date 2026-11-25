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

import re
from dataclasses import dataclass, field, replace
from uuid import UUID

import numpy as np
from typing_extensions import Any, Dict, List, Optional

from coraplex.datastructures.enums import DetectionGrounding
from coraplex.perception import PerceptionInterface
from coraplex.querying.predicates import GripperHolds
from coraplex.robot_plans.actions.core.pick_up import PickUpAction
from coraplex.robot_plans.actions.core.placing import PlaceAction
from coraplex.plans.failures import MotionMadeNoProgress, MotionWouldBreakSafetyLimit
from coraplex.plans.validation import (
    FailureCause,
    PlanValidation,
    StepCheck,
    ValidationVerdict,
)
from cramera_bridge.exceptions import (
    NoArmCarriesObject,
    PickOfHeldObject,
    PlaceBeforePick,
    PlacementNotFound,
)
from cramera_bridge.geometry import NumericPose
from cramera_bridge.live.perception_images import PerceptionCamera, SeenImage
from cramera_bridge.names import ENUM_NAMES
from cramera_bridge.performing import TaskContext
from cramera_bridge.plans.actions import DiscoveredActions
from cramera_bridge.plans.arms import Arms, RobotArms
from cramera_bridge.plans.detected_objects import DetectedObjects
from cramera_bridge.plans.perception_reports import object_name
from cramera_bridge.plans.safety import WORKSPACE_MARGIN, RobotSafety
from cramera_bridge.plans.site import RobotSite
from cramera_bridge.plans.steps import StepActions, StepArguments
from cramera_protocol.detection import DetectedObjectReference
from cramera_protocol.plan_builder import Destination, PlacementMode, PlanStep
from cramera_protocol.robot_profile import SafetyLimits
from cramera_protocol.validation import (
    StepFailureReason,
    StepValidation,
    StepVerdict,
)
from giskardpy.motion_statechart.exceptions import (
    NoProgressError,
    SafetyConstraintViolated,
)
from giskardpy.motion_statechart.monitors.safety_monitors import SafetyEnvelope
from semantic_digital_twin.robots.robot_parts import Arm
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

# %% one step


STALLED = "stalled before reaching its goal"
"""
What a person reads for a motion that stopped approaching its goal.
"""

BOUND_PASSED = re.compile(
    r"(?P<distance>[\d.]+) mm past the box's (?P<side>lower|upper) (?P<axis>[xyz]) bound"
)
"""
How Giskard's workspace monitor says how far a tool left its box, see
:meth:`~giskardpy.motion_statechart.monitors.safety_monitors.SafetyEnvelope.describe_violation`.
"""


def failure_text(failure: Exception, full: bool = False) -> str:
    """
    :param failure: Why a step failed.
    :param full: Whether it stands on its own, as on a step's card: CRAM's suggestion
        is kept on its own line and a broken safety constraint is named.
    :return: Its error as a person reads it; a stalled motion or a tool past its
        workspace box is said shortly, without CRAM's suggestion.
    """
    if isinstance(failure, (MotionMadeNoProgress, NoProgressError)):
        return STALLED
    if isinstance(failure, MotionWouldBreakSafetyLimit):
        failure = failure.violation
    if isinstance(failure, SafetyConstraintViolated):
        past = BOUND_PASSED.search(failure.violation)
        if past is None:
            return f"breaks {failure.constraint}"
        passed = f"{past['distance']} mm past its {past['side']} {past['axis']} bound"
        return f"{failure.constraint.split(',')[0]}: {passed}" if full else passed
    return str(failure) if full else str(failure).partition("\nSuggestion: ")[0]


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

    images: List[SeenImage] = field(default_factory=list)
    """
    What a detection step saw when it was grounded.
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

    def failure_text(self) -> str:
        """
        :return: What failed the step, as a person reads it; empty when it did not fail.
        """
        if self.check is None or self.check.failure is None:
            return ""
        return failure_text((self.check.candidate_failures or [self.check.failure])[0])

    def to_step_validation(self) -> StepValidation:
        """
        :return: How the step fared, in the protocol's words.
        """
        arm = None if self.arm is None else ENUM_NAMES.member_identifier(Arms, self.arm)
        if self.check is None:
            return StepValidation(
                step=self.step.identifier, verdict=StepVerdict.UNCHECKED
            )
        images = [image.to_inline_image() for image in self.images]
        if self.check.verdict is ValidationVerdict.ASSUMED:
            return StepValidation(
                step=self.step.identifier,
                verdict=StepVerdict.ASSUMED,
                arm=arm,
                images=images,
            )
        if self.check.verdict is ValidationVerdict.VALID:
            return StepValidation(
                step=self.step.identifier,
                verdict=StepVerdict.VALID,
                arm=arm,
                images=images,
            )
        failure = (self.check.candidate_failures or [self.check.failure])[0]
        return StepValidation(
            step=self.step.identifier,
            verdict=StepVerdict.FAILED,
            reason=self.translate_cause(self.check.cause),
            detail=failure_text(failure, full=True),
            images=images,
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
            case FailureCause.SAFETY_LIMIT:
                return StepFailureReason.SAFETY_LIMIT
        return StepFailureReason.UNSUCCESSFUL


@dataclass
class EveryArmFailed(StepCheck):
    """
    How a step leaving its arm open fared when every arm failed it or a step after it
    that the arm's object is carried through.
    """

    first_cause: Optional[FailureCause] = None
    """
    Why the nearer arm failed, which the step reports as its cause.
    """

    @property
    def cause(self) -> Optional[FailureCause]:
        return self.first_cause


@dataclass
class RefusedStep(StepCheck):
    """
    How a step fared that was refused before it was tried, for a cause its failure alone
    does not tell.
    """

    refusal: Optional[FailureCause] = None
    """
    Why the step was refused.
    """

    @property
    def cause(self) -> Optional[FailureCause]:
        return self.refusal


# %% returning the copy to an earlier point


@dataclass
class CopySnapshot:
    """
    The model version and the state of the copy a plan is grounded in, and the objects
    the plan names in it, at one point, to which the grounding can return to try another
    arm.
    """

    world: World
    """
    The copy.
    """

    model_version: int
    """
    The copy's model version at that point.
    """

    states: Dict[UUID, np.ndarray]
    """
    The state of every degree of freedom of the copy at that point.
    """

    bodies: Dict[str, Body]
    """
    The plan's objects by their identity and reference at that point.
    """

    @classmethod
    def capture(cls, world: World, bodies: Dict[str, Body]) -> CopySnapshot:
        """
        :param world: The copy.
        :param bodies: The plan's objects in it.
        :return: A snapshot of the copy as it is now.
        """
        return cls(
            world=world,
            model_version=world.get_world_model_manager().version,
            states={
                identifier: values.copy() for identifier, values in world.state.items()
            },
            bodies=dict(bodies),
        )

    def restore(self, bodies: Dict[str, Body]) -> None:
        """
        Undo every model change of the copy since the snapshot, and return its state and
        the plan's objects to theirs.

        :param bodies: The plan's objects in the copy, set back in place.
        """
        self.world.rollback_to_version(self.model_version)
        for identifier, values in self.states.items():
            self.world.state[identifier] = values
        self.world.notify_state_change()
        bodies.clear()
        bodies.update(self.bodies)


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

    safety: Optional[SafetyLimits] = None
    """
    The safety limits of the robot profile, whose workspace boxes every motion is held
    inside, a margin inside their edges; None holds the motions to none.
    """

    camera: Optional[PerceptionCamera] = None
    """
    Takes the images of what each detection step saw; None takes none.
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

    workspaces: SafetyEnvelope = field(init=False, default_factory=SafetyEnvelope)
    """
    The workspace boxes of :attr:`safety` in the copy, a margin inside their edges
    except where a tool already stands nearer to an edge, as the copy stands when the
    steps are grounded, see :meth:`ground`.
    """

    step_numbers: Dict[str, int] = field(init=False, default_factory=dict)
    """
    The number of each step given to :meth:`ground` by its identity, counted from one
    in the order they were given.
    """

    picked_at: Dict[str, int] = field(init=False, default_factory=dict)
    """
    For each object a grounded step picked up, the number of the last step that did, see
    :attr:`step_numbers`.
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
        :param steps: The steps of the performing robot, in order, starting where the
            copy stands now, which may have been put where the real robot stands after
            the grounding was made.
        :return: How each was grounded; those after the first that failed are not
            tried. Where an arm stands outside its workspace box, the first step fails
            saying so, since the run would be stopped at its first motion.
        """
        if self.safety is not None:
            safety = RobotSafety(limits=self.safety, site=self.site)
            self.workspaces = safety.workspace_check(self.copied_context)
            outside = safety.arm_outside_its_workspace(self.copied_context)
            if outside is not None and steps:
                return [
                    GroundedStep(
                        step=steps[0],
                        check=RefusedStep(
                            verdict=ValidationVerdict.FAILED,
                            failure=outside,
                            refusal=FailureCause.SAFETY_LIMIT,
                        ),
                    ),
                    *[GroundedStep(step=step) for step in steps[1:]],
                ]
        self.step_numbers = {
            step.identifier: number for number, step in enumerate(steps, start=1)
        }
        grounded: List[GroundedStep] = []
        position = 0
        while position < len(steps):
            if grounded and not grounded[-1].succeeded:
                grounded.append(GroundedStep(step=steps[position]))
                position += 1
                continue
            out_of_order = self.find_place_before_pick(
                steps[position]
            ) or self.find_pick_of_held_object(steps[position])
            if out_of_order is not None:
                grounded.append(
                    GroundedStep(
                        step=steps[position],
                        check=StepCheck(
                            verdict=ValidationVerdict.FAILED, failure=out_of_order
                        ),
                    )
                )
                position += 1
                continue
            carried = self.carried_steps(steps, position)
            if len(self.arms_to_try(steps[position])) > 1:
                grounded.extend(self.ground_with_an_arm(carried))
            else:
                grounded.append(self.ground_step(steps[position]))
                carried = carried[:1]
            position += len(carried)
        return grounded

    def find_place_before_pick(self, step: PlanStep) -> Optional[PlaceBeforePick]:
        """
        :param step: The next step of the performing robot, not carried through by an
            arm a step before it was given.
        :return: Why the step fails when it puts down an object of the plan that no
            arm of the copy holds, since no step before it picked the object up; None
            otherwise.
        """
        if not issubclass(self.actions.named(step.action).action_class, PlaceAction):
            return None
        arguments = self.arguments(step)
        body = arguments.acted_on()
        if body is None or any(
            GripperHolds(arm.end_effector, body)()
            for arm in self.copied_context.robot.all_arms
        ):
            return None
        return PlaceBeforePick(arguments.object_identifier())

    def picks_up(self, step: PlanStep) -> bool:
        """
        :param step: A step of the performing robot.
        :return: Whether the step picks an object up.
        """
        return issubclass(self.actions.named(step.action).action_class, PickUpAction)

    def find_pick_of_held_object(self, step: PlanStep) -> Optional[PickOfHeldObject]:
        """
        :param step: The next step of the performing robot, not carried through by an
            arm a step before it was given.
        :return: Why the step fails when it picks up an object an arm of the copy
            already holds, since a step before it picked the object up and none put it
            down since; None otherwise.
        """
        if not self.picks_up(step):
            return None
        arguments = self.arguments(step)
        body = arguments.acted_on()
        if body is None or not any(
            GripperHolds(arm.end_effector, body)()
            for arm in self.copied_context.robot.all_arms
        ):
            return None
        identifier = arguments.object_identifier()
        return PickOfHeldObject(
            object_identifier=identifier, held_since=self.picked_at.get(identifier)
        )

    def arguments(self, step: PlanStep) -> StepArguments:
        """
        :param step: A step of the performing robot.
        :return: Its arguments in the copy as it is now.
        """
        return StepArguments(
            context=self.copied_context,
            bodies=self.copied_bodies,
            action=self.actions.named(step.action),
            step=step,
            site=self.site,
        )

    def arms_to_try(self, step: PlanStep) -> List[Arm]:
        """
        :param step: A step of the performing robot.
        :return: The arms of the robot a step leaving its arm open may be given, those
            nearer the object it acts on first; none for a step choosing its arms itself
            or a detection.
        """
        if self.actions.named(step.action).looks_for_objects():
            return []
        arguments = self.arguments(step)
        if arguments.find_open_arm_field() is None:
            return []
        return RobotArms(self.copied_context.robot, near=arguments.acted_on()).arms(
            Arms.AUTOMATIC
        )

    def carried_steps(self, steps: List[PlanStep], position: int) -> List[PlanStep]:
        """
        :param steps: The steps of the performing robot, in order.
        :param position: The position of a step.
        :return: The step, and, when it leaves its arm open, the steps after it up to
            the first that puts down the object it acts on, which the arm carries it
            through; only the step when a step picks the object up again before one
            puts it down, which then fails on its own, see
            :meth:`find_pick_of_held_object`.
        """
        if not self.arms_to_try(steps[position]):
            return steps[position : position + 1]
        carried = self.arguments(steps[position]).object_identifier()
        for end in range(position + 1, len(steps)):
            if self.puts_down(steps[end], carried):
                return steps[position : end + 1]
            if self.picks_up(steps[end]) and (
                self.arguments(steps[end]).object_identifier() == carried
            ):
                break
        return steps[position : position + 1]

    def puts_down(self, step: PlanStep, identifier: Optional[str]) -> bool:
        """
        :param step: A step of the performing robot.
        :param identifier: The identity of an object, or a reference to one.
        :return: Whether the step puts that object down somewhere.
        """
        if identifier is None or self.actions.named(step.action).looks_for_objects():
            return False
        arguments = self.arguments(step)
        return arguments.object_identifier() == identifier and any(
            offered.accepts_surface and offered.name in step.values
            for offered in arguments.action.schema.fields
        )

    def ground_with_an_arm(self, carried: List[PlanStep]) -> List[GroundedStep]:
        """
        :param carried: A step leaving its arm open, and the steps its arm carries the
            object through, see :meth:`carried_steps`.
        :return: How they were grounded with the first arm, nearer ones first, that
            succeeds in each; when none does, the step failing with why each arm failed,
            unless an arm carried the object to a place that is not found, such as one
            another object stands on, which no other arm changes, or every arm took the
            object and failed the same later step: then the grounding of the first such
            arm, which reports the failure at the later step.
        """
        opening, *later = carried
        arguments = self.arguments(opening)
        open_field = arguments.find_open_arm_field()
        body = arguments.acted_on()
        name = object_name(str(body.name.name))
        reference = DetectedObjectReference.from_value(
            arguments.object_identifier() or ""
        )
        if reference is not None:
            name = f"{name} (detected in {reference.step.replace('_', ' ')})"
        robot_arms = RobotArms(self.copied_context.robot)
        attempts: List[List[GroundedStep]] = []
        for arm in self.arms_to_try(opening):
            snapshot = CopySnapshot.capture(
                self.copied_context.world, self.copied_bodies
            )
            side = robot_arms.find_side(arm)
            pinned = replace(
                opening,
                values={
                    **opening.values,
                    open_field: ENUM_NAMES.member_identifier(Arms, side),
                },
            )
            attempt = [
                replace(
                    self.ground_step(pinned),
                    step=opening,
                    arm=side,
                    arm_field=open_field,
                )
            ]
            for step in later:
                if not attempt[-1].succeeded:
                    break
                attempt.append(self.ground_step(step))
            if attempt[-1].succeeded:
                return attempt
            attempts.append(attempt)
            snapshot.restore(self.copied_bodies)
        for attempt in attempts:
            if isinstance(attempt[-1].check.failure, PlacementNotFound) or (
                len(attempt) > 1
                and all(len(other) == len(attempt) for other in attempts)
            ):
                return [
                    *attempt,
                    *[GroundedStep(step=step) for step in carried[len(attempt) :]],
                ]
        failures = [
            f"{ENUM_NAMES.member_identifier(Arms, attempt[0].arm)} arm"
            + (
                ""
                if attempt[-1].step is opening
                else f" at {attempt[-1].step.identifier.replace('_', ' ')}"
            )
            + f": {attempt[-1].failure_text()}"
            for attempt in attempts
        ]
        return [
            GroundedStep(
                step=opening,
                check=EveryArmFailed(
                    verdict=ValidationVerdict.FAILED,
                    failure=NoArmCarriesObject(
                        object_name=name,
                        destination=self.destination_text(carried[-1]),
                        failures=failures,
                        cause=self.workspace_cause(body, carried[-1]),
                    ),
                    first_cause=attempts[0][-1].check.cause,
                ),
            ),
            *[GroundedStep(step=step) for step in later],
        ]

    def workspace_cause(self, body: Body, step: PlanStep) -> Optional[str]:
        """
        :param body: The carried object in the copy, where it lies before it is taken.
        :param step: The step putting it down.
        :return: That the object lies only in the workspaces of arms none of which
            reaches where it is put down, such as "it lies at y = -0.41 m, only in
            the right arm's workspace, and left_tray only in the left arm's"; None
            when the workspaces do not tell why every arm failed.
        """
        destination = self.destination_point(step)
        if self.safety is None or destination is None:
            return None
        plan_T_world = np.linalg.inv(
            RobotSafety(limits=self.safety, site=self.site).world_T_plan()
        )
        picked = (
            plan_T_world
            @ [
                *NumericPose.of_entity(self.copied_context.world, body).position[:3],
                1.0,
            ]
        )[:2]
        put = (plan_T_world @ [*destination, 1.0])[:2]

        def arms_reaching(point: np.ndarray) -> List[str]:
            return [
                workspace.arm
                for workspace in self.safety.workspaces
                if workspace.box.min_x + WORKSPACE_MARGIN
                <= point[0]
                <= workspace.box.max_x - WORKSPACE_MARGIN
                and workspace.box.min_y + WORKSPACE_MARGIN
                <= point[1]
                <= workspace.box.max_y - WORKSPACE_MARGIN
            ]

        at_pick, at_put = arms_reaching(picked), arms_reaching(put)
        if not at_pick or not at_put or set(at_pick) & set(at_put):
            return None
        where = self.destination_text(step).split(" ", 1)[-1]
        return (
            f"it lies at y = {picked[1]:.2f} m, only in the {' and '.join(at_pick)} "
            f"arm's workspace, and {where} only in the {' and '.join(at_put)} arm's"
        )

    def destination_point(self, step: PlanStep) -> Optional[List[float]]:
        """
        :param step: A step of the performing robot.
        :return: Where in the world it puts its object down, at a zone's middle; None
            when it puts none down or the place is only found when grounded.
        """
        for offered in self.actions.named(step.action).schema.fields:
            if not offered.accepts_surface or offered.name not in step.values:
                continue
            destination = Destination.from_json(step.values[offered.name])
            if destination.placement is PlacementMode.ZONE:
                area = self.site.zone(destination.zone).area
                plan_point = [
                    (area.min_x + area.max_x) / 2,
                    (area.min_y + area.max_y) / 2,
                    0.0,
                    1.0,
                ]
                world_T_plan = RobotSafety(
                    limits=self.safety, site=self.site
                ).world_T_plan()
                return list((world_T_plan @ plan_point)[:3])
            if destination.placement is PlacementMode.ON_TOP_OF:
                support = self.copied_bodies.get(destination.object)
                if support is None:
                    return None
                return list(
                    NumericPose.of_entity(self.copied_context.world, support).position[
                        :3
                    ]
                )
            if destination.pose is not None:
                return [destination.pose.x, destination.pose.y, destination.pose.z]
        return None

    def destination_text(self, step: PlanStep) -> str:
        """
        :param step: A step of the performing robot.
        :return: Where the step puts its object down, as a person reads it; where it
            leaves it when it puts none down.
        """
        for offered in self.actions.named(step.action).schema.fields:
            if not offered.accepts_surface or offered.name not in step.values:
                continue
            destination = Destination.from_json(step.values[offered.name])
            if destination.placement is PlacementMode.ZONE:
                return f"into {destination.zone}"
            if destination.placement is PlacementMode.ON_TOP_OF:
                return f"on top of {destination.object}"
            if destination.pose is not None:
                return f"at ({destination.pose.x:.2f}, {destination.pose.y:.2f})"
        return f"where {step.identifier} leaves it"

    def ground_step(self, step: PlanStep) -> GroundedStep:
        """
        :param step: The next step of the performing robot.
        :return: How it was grounded where the steps before it left the copy.
        """
        if self.actions.named(step.action).looks_for_objects():
            return self.ground_detection(step)
        arguments = self.arguments(step)
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
            ).action(replace(step, values={**step.values, **resolved})),
            safety=self.workspaces,
        )
        if (
            self.picks_up(step)
            and check.verdict is not ValidationVerdict.FAILED
            and step.identifier in self.step_numbers
        ):
            self.picked_at[arguments.object_identifier()] = self.step_numbers[
                step.identifier
            ]
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
        if self.camera is not None:
            self.camera.observe_started()
        check = self.validation.check_detection(query)
        if check.found:
            self.copied_bodies[DetectedObjectReference(step.identifier).text] = (
                check.found[0]
            )
        images = (
            self.camera.images(
                self.copied_context.world, self.copied_context.robot, check.found
            )
            if self.camera is not None
            and check.grounding is DetectionGrounding.PERCEIVED
            else []
        )
        return GroundedStep(step=step, check=check, images=images)
