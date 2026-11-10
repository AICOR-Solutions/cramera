"""
Running the performing robot's steps with a budget of retries.

Each step first checks that the objects it expects in place still lie where the plan was
grounded with them, and a step keeping an object in view runs beside a monitor of the
robot's camera that gives the step up once the object leaves its field of view. A step
that fails is attempted again from where the run stopped, the steps after it grounded
anew: with the other arm first where a motion failed, after detecting its objects again
where they were lost track of. Once a step used up its attempts the plan is aborted.
Every step as it is scheduled and starts, every attempt, every change of what the camera
keeps in view, every object a step perceived and a safety stop go to the run log.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

from typing_extensions import Callable, Dict, List, Optional, Sequence

from coraplex.datastructures.enums import DetectionTechnique
from coraplex.exceptions import MotionDidNotFinish, NothingPerceived
from coraplex.perception import PerceptionTask, WorldPerception
from coraplex.plans.expected_positions import BodiesWhereExpected, ExpectedPosition
from coraplex.plans.failures import BodiesMovedSinceGrounding, TargetLeftFieldOfView
from coraplex.plans.validation import FailureCause
from coraplex.robot_plans.actions.core.misc import DetectAction
from cramera_bridge.exceptions import StepAbandoned
from cramera_bridge.names import ENUM_NAMES
from cramera_bridge.performing import PlanPerformance, TaskContext
from cramera_bridge.plans.actions import DiscoveredActions
from cramera_bridge.plans.arms import Arms
from cramera_bridge.plans.grounding import GroundedStep, PlanGrounding
from cramera_bridge.plans.regions import RegionBoxes
from cramera_bridge.plans.run_log import (
    AttemptOutcome,
    LookAt,
    ObjectPerceived,
    RunLog,
    SafetyStopped,
    StepAttempt,
    StepScheduled,
    StepStarted,
    View,
)
from cramera_bridge.plans.site import RobotSite
from cramera_bridge.plans.steps import StepActions, StepArguments
from cramera_bridge.plans.world import PlannedGraspable
from cramera_protocol.detection import DetectedObjectReference, DetectionRegion
from cramera_protocol.live_messages import ConstraintMonitorType, MonitorParameterKey
from cramera_protocol.plan_builder import PlanStep, StepConstraint
from cramph.composites import CancelledWhenTrue
from cramph.composites import Sequence as StepSequence
from cramph.data_types import LifeCycleValues, ObservationStateValues
from cramph.exceptions import ExecutionFailure
from cramph.executor import (
    ExecutorExtension,
    StatechartExecutor,
    TickingExecutorExtension,
)
from cramph.node import StatechartNode
from giskardpy.motion_statechart.monitors.cartesian_monitors import OutOfFieldOfView
from giskardpy.motion_statechart.monitors.safety_monitors import (
    CancelOnSafetyViolation,
)
from krrood_spatial_math.spatial_types import Point3
from semantic_digital_twin.world_description.color_names import ColorName
from semantic_digital_twin.world_description.world_entity import Body

# %% steps as they run


@dataclass(frozen=True)
class ScheduledStep:
    """
    A step of the performing robot as it runs next.
    """

    step: PlanStep
    """
    The step as the plan names it.
    """

    resolved: PlanStep
    """
    The step as it was grounded: naming the arm and the poses its grounding chose.
    """

    expected_positions: Dict[str, List[float]] = field(default_factory=dict)
    """
    Where the objects the step expects in place lay when it was grounded, by identity.
    """

    @classmethod
    def from_grounded_step(cls, grounded: GroundedStep) -> ScheduledStep:
        """
        :param grounded: A step that succeeded its grounding.
        :return: The step as it runs.
        """
        return cls(
            step=grounded.step,
            resolved=grounded.resolved_step(),
            expected_positions=dict(grounded.expected_positions),
        )

    def look_at(self) -> Optional[StepConstraint]:
        """
        :return: The step's first constraint keeping an object in the camera's view, or
            None.
        """
        for constraint in self.step.constraints:
            if (
                constraint.monitor is not None
                and constraint.monitor.monitor_type
                is ConstraintMonitorType.IN_FIELD_OF_VIEW
            ):
                return constraint
        return None


# %% why an attempt failed


class Alternative(StrEnum):
    """
    How the next attempt at a failed step differs from the one before.
    """

    OTHER_ARM = "takes the other arm"
    """
    The step's arm, left to its grounding, is the robot's other one.
    """

    REDETECTION = "detects its objects again and grounds the plan anew"
    """
    The step's objects are detected again on the table and the rest of the plan is
    grounded where they were found.
    """


@dataclass(frozen=True)
class FailedAttempt:
    """
    Why an attempt at a step failed.
    """

    reason: str
    """
    The failure, as a person reads it.
    """

    lost_track: bool
    """
    Whether the step's objects were not where the plan held them, so detecting them
    again comes before anything else.
    """

    @classmethod
    def from_failure(
        cls, failure: ExecutionFailure, node: StatechartNode
    ) -> FailedAttempt:
        """
        :param failure: What ended the run of the attempt.
        :param node: The node the attempt ran as.
        :return: Why it failed; a plan that did not finish because a detection below
            the node saw nothing failed as not perceived.
        """
        if isinstance(failure, MotionDidNotFinish):
            failure = next(
                (
                    NothingPerceived(task.query.semantic_annotation)
                    for task in [node, *node.descendants]
                    if isinstance(task, PerceptionTask)
                    and task.life_cycle_state is LifeCycleValues.FAILED
                ),
                failure,
            )
        return cls(
            reason=failure.error_message(),
            lost_track=isinstance(
                failure,
                (BodiesMovedSinceGrounding, NothingPerceived, TargetLeftFieldOfView),
            ),
        )

    @classmethod
    def from_grounded_step(cls, grounded: GroundedStep) -> FailedAttempt:
        """
        :param grounded: A step that failed its grounding.
        :return: Why it failed.
        """
        validation = grounded.to_step_validation()
        return cls(
            reason=(
                f"{validation.step} cannot be grounded ({validation.reason}): "
                f"{validation.detail}"
            ),
            lost_track=grounded.check.cause is FailureCause.NOT_PERCEIVED,
        )


# %% following an attempt


@dataclass(frozen=True)
class AttemptedStep:
    """
    A step's node in the plan of an attempt.
    """

    node: StatechartNode
    """
    The node the step runs as.
    """

    step: str
    """
    The identity of the step.
    """

    number: int
    """
    Which attempt at the step the node is.
    """

    arm: Optional[str] = None
    """
    The arm the attempt uses, by the protocol's identifier; None when its grounding
    chose none.
    """

    detected: Optional[DetectedObject] = None
    """
    The object the step perceives: the one a detection step finds for later steps, else
    the one the step acts on, such as a pick's; written as perceived once the step
    succeeded after a perception below it did.
    """

    def has_perceived(self) -> bool:
        """
        :return: Whether a perception below the step's node succeeded.
        """
        return any(
            isinstance(node, PerceptionTask)
            and node.life_cycle_state is LifeCycleValues.SUCCEEDED
            for node in self.node.descendants
        )


@dataclass(frozen=True)
class DetectedObject:
    """
    The object a step perceives.
    """

    step: str
    """
    The identity of the step.
    """

    target: str
    """
    The identity of the object.
    """

    body: Body
    """
    The object's body, whose color perception updates.
    """

    def perceived(self) -> ObjectPerceived:
        """
        :return: The object as perceived now, with the one color it shows, if any.
        """
        colors = self.body.visual.color_names()
        return ObjectPerceived(
            step=self.step,
            target=self.target,
            color=(
                ENUM_NAMES.member_identifier(ColorName, next(iter(colors)))
                if len(colors) == 1
                else None
            ),
        )


@dataclass(frozen=True)
class WatchedTarget:
    """
    The monitor of a step's look-at.
    """

    monitor: OutOfFieldOfView
    """
    The monitor observing whether the target left the camera's view.
    """

    step: str
    """
    The identity of the step.
    """

    target: str
    """
    The identity of the object kept in view.
    """


@dataclass
class AttemptProgress(TickingExecutorExtension):
    """
    Writes to the run log every step of an attempt's plan that succeeded, every change
    of what a step's look-at observes, and a safety stop that cancelled the plan.
    """

    run_log: RunLog
    """
    The run log.
    """

    attempts: int
    """
    How many attempts a step has at most.
    """

    steps: List[AttemptedStep] = field(default_factory=list)
    """
    The steps of the plan.
    """

    watched: List[WatchedTarget] = field(default_factory=list)
    """
    The look-ats of the plan.
    """

    succeeded: set[str] = field(default_factory=set, init=False)
    """
    The identities of the steps whose success was written.
    """

    started: set[str] = field(default_factory=set, init=False)
    """
    The identities of the steps whose start was written.
    """

    views: Dict[str, View] = field(default_factory=dict, init=False)
    """
    What each step's look-at observed last, by the step's identity.
    """

    def after_tick(self, executor: StatechartExecutor) -> None:
        for attempted in self.steps:
            self.write_success(attempted)
        # the steps run one after another, so the first that did not succeed runs
        current = next(
            (
                attempted
                for attempted in self.steps
                if attempted.node.life_cycle_state is not LifeCycleValues.SUCCEEDED
            ),
            None,
        )
        if current is not None:
            self.write_start(current)
        for watched in self.watched:
            self.write_view(watched)

    def write_start(self, attempted: AttemptedStep) -> None:
        """
        :param attempted: A step of the plan that started, written once.
        """
        if attempted.step in self.started:
            return
        self.started.add(attempted.step)
        self.run_log.write(
            StepStarted(
                step=attempted.step,
                number=attempted.number,
                attempts=self.attempts,
                arm=attempted.arm,
            )
        )

    def after_run(self, executor: StatechartExecutor) -> None:
        for attempted in self.steps:
            self.write_success(attempted)
        self.write_safety_stop(executor)

    def write_safety_stop(self, executor: StatechartExecutor) -> None:
        """
        :param executor: The executor whose run stopped; when a motion broke a safety
            limit, which cancelled the run, the step whose motion it was and the stop
            are written.
        """
        stop = next(
            (
                node
                for node in executor.statechart.get_nodes_by_type(
                    CancelOnSafetyViolation
                )
                if node.life_cycle_state is not LifeCycleValues.NOT_STARTED
            ),
            None,
        )
        if stop is None:
            return
        constraint = stop.create_exception().constraint
        # the steps run one after another, so the first that did not succeed was stopped
        attempted = next(
            attempted
            for attempted in self.steps
            if attempted.node.life_cycle_state is not LifeCycleValues.SUCCEEDED
        )
        self.run_log.write(
            StepAttempt(
                step=attempted.step,
                number=attempted.number,
                attempts=self.attempts,
                outcome=AttemptOutcome.STOPPED,
                reason=constraint,
                arm=attempted.arm,
            )
        )
        self.run_log.write(SafetyStopped(constraint=constraint, step=attempted.step))

    def write_success(self, attempted: AttemptedStep) -> None:
        """
        :param attempted: A step of the plan, written once it succeeded.
        """
        if attempted.step in self.succeeded:
            return
        if attempted.node.life_cycle_state is not LifeCycleValues.SUCCEEDED:
            return
        self.write_start(attempted)
        self.succeeded.add(attempted.step)
        if attempted.detected is not None and attempted.has_perceived():
            self.run_log.write(attempted.detected.perceived())
        self.run_log.write(
            StepAttempt(
                step=attempted.step,
                number=attempted.number,
                attempts=self.attempts,
                outcome=AttemptOutcome.SUCCEEDED,
                arm=attempted.arm,
            )
        )

    def write_view(self, watched: WatchedTarget) -> None:
        """
        :param watched: A look-at of the plan, written when what it observes changed
            while it runs.
        """
        if watched.monitor.life_cycle_state is not LifeCycleValues.RUNNING:
            return
        observation = watched.monitor.observation_state
        if observation == ObservationStateValues.UNKNOWN:
            return
        view = (
            View.OUT_OF_VIEW
            if observation == ObservationStateValues.TRUE
            else View.IN_VIEW
        )
        if self.views.get(watched.step) is view:
            return
        self.views[watched.step] = view
        self.run_log.write(LookAt(step=watched.step, target=watched.target, view=view))


@dataclass(frozen=True)
class AttemptPlan:
    """
    The plan of one attempt: the steps from the one attempted on, one node each.
    """

    first: int
    """
    The position of the first step among all steps.
    """

    plan: StepSequence
    """
    The plan.
    """

    progress: AttemptProgress
    """
    Writes the plan's progress to the run log.
    """

    def failed_position(self) -> int:
        """
        :return: The position, among all steps, of the step the plan stopped at.
        """
        offset = next(
            index
            for index, node in enumerate(self.plan.nodes)
            if node.life_cycle_state is not LifeCycleValues.SUCCEEDED
        )
        return self.first + offset


# %% the run


@dataclass
class StepRun:
    """
    Runs the performing robot's steps, attempting a failed step again until it used up
    its attempts.
    """

    context: TaskContext
    """
    The world and the robot that performs the steps.
    """

    bodies: Dict[str, Body]
    """
    The plan's objects by identity, and the objects detection steps find by the
    references later steps name them with.
    """

    actions: DiscoveredActions
    """
    The workspace's actions, which steps name.
    """

    site: RobotSite = field(default_factory=RobotSite)
    """
    Where the plan stands the robot, and the robot profile's zones.
    """

    run_log: RunLog = field(default_factory=RunLog)
    """
    Where every attempt is written.
    """

    retries: int = 2
    """
    How often a failed step is attempted again before the plan is aborted.
    """

    regrounding_distance: float = 0.02
    """
    How far, in metres, an object a step expects in place may lie from where the plan
    was grounded with it before the step is grounded anew.
    """

    steps: List[ScheduledStep] = field(default_factory=list)
    """
    The steps as they run, each as it was grounded last.
    """

    attempt_numbers: Dict[str, int] = field(default_factory=dict)
    """
    Which attempt each step is at, by the step's identity; the first when it is absent.
    """

    @property
    def attempts(self) -> int:
        """
        How many attempts a step has at most.
        """
        return self.retries + 1

    # %% grounding

    def grounding(self) -> PlanGrounding:
        """
        :return: A grounding of steps in a copy of the world as it is now, on the
            twin's objects.
        """
        return PlanGrounding(
            context=self.context,
            bodies=dict(self.bodies),
            actions=self.actions,
            perception=WorldPerception(reports_unseen_bodies=True),
            site=self.site,
        )

    # %% building an attempt

    def attempt_plan(self, first: int) -> AttemptPlan:
        """
        :param first: The position of the step attempted next.
        :return: The plan of that step and the steps after it.
        """
        progress = AttemptProgress(run_log=self.run_log, attempts=self.attempts)
        nodes = []
        for scheduled in self.steps[first:]:
            node = self.step_node(scheduled, progress)
            identifier = scheduled.step.identifier
            progress.steps.append(
                AttemptedStep(
                    node=node,
                    step=identifier,
                    number=self.attempt_numbers.get(identifier, 1),
                    arm=self.arm_of(scheduled),
                    detected=self.detected_by(scheduled),
                )
            )
            nodes.append(node)
        return AttemptPlan(
            first=first, plan=StepSequence(nodes=nodes), progress=progress
        )

    def step_node(
        self, scheduled: ScheduledStep, progress: AttemptProgress
    ) -> StatechartNode:
        """
        :param scheduled: A step.
        :param progress: Learns of the step's look-at.
        :return: The step's action, beside the monitor of its look-at, after the check
            of the objects it expects in place.
        """
        node = StepActions(
            self.context, self.bodies, self.actions, site=self.site
        ).action(scheduled.resolved)
        look_at = scheduled.look_at()
        if look_at is not None:
            target = look_at.monitor.parameters[MonitorParameterKey.TARGET]
            camera = self.context.robot.get_default_camera()
            monitor = OutOfFieldOfView(
                camera=camera,
                target=self.bodies[target],
                margin=look_at.monitor.parameters.get(MonitorParameterKey.MARGIN, 0.0),
            )
            progress.watched.append(
                WatchedTarget(
                    monitor=monitor, step=scheduled.step.identifier, target=target
                )
            )
            node = CancelledWhenTrue(
                monitor=monitor,
                monitored_node=node,
                exception=TargetLeftFieldOfView(
                    camera=camera, target=self.bodies[target]
                ),
            )
        expected = [
            ExpectedPosition(
                body=self.bodies[identifier],
                position=Point3(*position, reference_frame=self.context.world.root),
            )
            for identifier, position in scheduled.expected_positions.items()
        ]
        if not expected:
            return node
        return StepSequence(
            nodes=[
                BodiesWhereExpected(
                    expected=expected, tolerance=self.regrounding_distance
                ),
                node,
            ]
        )

    # %% reporting

    def announce(self) -> None:
        """
        Write every step as scheduled, with the arm its grounding chose.
        """
        for scheduled in self.steps:
            self.run_log.write(
                StepScheduled(
                    step=scheduled.step.identifier, arm=self.arm_of(scheduled)
                )
            )

    def arm_of(self, scheduled: ScheduledStep) -> Optional[str]:
        """
        :param scheduled: A step.
        :return: The arm its grounding chose for it, by the protocol's identifier, when
            the step leaves its arm to be chosen; else None.
        """
        arguments = StepArguments(
            context=self.context,
            bodies=self.bodies,
            action=self.actions.named(scheduled.step.action),
            step=scheduled.step,
            site=self.site,
        )
        open_field = arguments.find_open_arm_field()
        if open_field is None:
            return None
        return scheduled.resolved.values.get(open_field)

    def detected_by(self, scheduled: ScheduledStep) -> Optional[DetectedObject]:
        """
        :param scheduled: A step.
        :return: The object the step perceives if it perceives one: the one it detects
            for later steps, when it is such a detection, else the one it acts on; None
            when it names no object.
        """
        reference = DetectedObjectReference(scheduled.step.identifier).text
        acted_on = StepArguments(
            context=self.context,
            bodies=self.bodies,
            action=self.actions.named(scheduled.step.action),
            step=scheduled.resolved,
            site=self.site,
        ).object_identifier()
        body = self.bodies.get(reference) or self.bodies.get(acted_on)
        if body is None:
            return None
        target = next(
            (
                identifier
                for identifier, named in self.bodies.items()
                if named is body
                and DetectedObjectReference.from_value(identifier) is None
            ),
            body.name.name,
        )
        return DetectedObject(step=scheduled.step.identifier, target=target, body=body)

    # %% running

    def perform(
        self,
        performance: PlanPerformance,
        extensions: Callable[[], Sequence[ExecutorExtension]],
        attempt: AttemptPlan,
    ) -> None:
        """
        Run every step, attempting a failed one again from where the run stopped.

        :param performance: How the plans are performed.
        :param extensions: Gives the executor extensions of each plan performed.
        :param attempt: The plan of the first attempt, from the first step on.
        :raises StepAbandoned: When a step failed every attempt it had.
        :raises SafetyConstraintViolated: When a motion broke a safety limit, which is
            no failure of the step and never attempted again; the attempt's progress
            wrote the stop to the run log.
        """
        while True:
            failure = self.perform_plan(
                attempt.plan, performance, [*extensions(), attempt.progress]
            )
            if failure is None:
                return
            position = attempt.failed_position()
            self.retry(
                position,
                FailedAttempt.from_failure(
                    failure, attempt.plan.nodes[position - attempt.first]
                ),
                performance,
                extensions,
            )
            attempt = self.attempt_plan(position)

    def perform_plan(
        self,
        plan: StatechartNode,
        performance: PlanPerformance,
        extensions: Sequence[ExecutorExtension],
    ) -> Optional[ExecutionFailure]:
        """
        :param plan: A plan of the run.
        :param performance: How it is performed.
        :param extensions: The executor extensions it runs with.
        :return: The failure that ended it, or None when it succeeded.
        """
        # A failed attempt is the run's to retry, as an action trial's is the
        # chooser's: the failure is caught where the next attempt is decided.
        try:
            performance.perform(plan, self.context, extensions)
        except ExecutionFailure as failure:
            return failure
        return None

    def retry(
        self,
        position: int,
        failed: FailedAttempt,
        performance: PlanPerformance,
        extensions: Callable[[], Sequence[ExecutorExtension]],
    ) -> None:
        """
        Prepare the next attempt at a failed step, as many times as preparing fails.

        :param position: The position of the failed step.
        :param failed: Why its attempt failed.
        :param performance: How the plans are performed.
        :param extensions: Gives the executor extensions of each plan performed.
        :raises StepAbandoned: When the step used up its attempts.
        """
        identifier = self.steps[position].step.identifier
        tried: List[Alternative] = []
        while True:
            number = self.attempt_numbers.get(identifier, 1)
            arm = self.arm_of(self.steps[position])
            if number >= self.attempts:
                self.run_log.write(
                    StepAttempt(
                        step=identifier,
                        number=number,
                        attempts=self.attempts,
                        outcome=AttemptOutcome.ABORTED,
                        reason=failed.reason,
                        arm=arm,
                    )
                )
                raise StepAbandoned(identifier, self.attempts, failed.reason)
            alternative = self.alternative(position, failed, tried)
            tried.append(alternative)
            self.run_log.write(
                StepAttempt(
                    step=identifier,
                    number=number,
                    attempts=self.attempts,
                    outcome=AttemptOutcome.RETRYING,
                    reason=failed.reason,
                    next_attempt=alternative.value,
                    arm=arm,
                )
            )
            self.attempt_numbers[identifier] = number + 1
            failed = self.prepare(position, alternative, performance, extensions)
            if failed is None:
                return

    def alternative(
        self, position: int, failed: FailedAttempt, tried: List[Alternative]
    ) -> Alternative:
        """
        :param position: The position of the failed step.
        :param failed: Why its attempt failed.
        :param tried: The alternatives tried for it since it failed in the run.
        :return: The other arm, unless the step lost track of its objects, leaves no
            arm to choose or took the other arm already; else detecting its objects
            again.
        """
        if (
            failed.lost_track
            or Alternative.OTHER_ARM in tried
            or self.other_arm_step(self.steps[position]) is None
        ):
            return Alternative.REDETECTION
        return Alternative.OTHER_ARM

    def prepare(
        self,
        position: int,
        alternative: Alternative,
        performance: PlanPerformance,
        extensions: Callable[[], Sequence[ExecutorExtension]],
    ) -> Optional[FailedAttempt]:
        """
        Ground the failed step and the steps after it anew as the alternative says.

        :param position: The position of the failed step.
        :param alternative: How the next attempt differs.
        :param performance: How the plans are performed.
        :param extensions: Gives the executor extensions of each plan performed.
        :return: Why preparing the attempt failed, or None when it is ready.
        """
        steps = [scheduled.step for scheduled in self.steps[position:]]
        if (
            alternative is Alternative.REDETECTION
            and self.steps[position].expected_positions
        ):
            detection = self.redetection(self.steps[position])
            failure = self.perform_plan(detection, performance, extensions())
            if failure is not None:
                lost = ", ".join(self.steps[position].expected_positions)
                return FailedAttempt(
                    reason=f"{lost} was not detected on the table again: "
                    f"{FailedAttempt.from_failure(failure, detection).reason}",
                    lost_track=True,
                )
        if alternative is Alternative.OTHER_ARM:
            steps[0] = self.other_arm_step(self.steps[position])
        grounded = self.grounding().ground(steps)
        for grounded_step in grounded:
            if not grounded_step.succeeded:
                return FailedAttempt.from_grounded_step(grounded_step)
        self.steps[position:] = [
            ScheduledStep.from_grounded_step(grounded_step)
            for grounded_step in grounded
        ]
        return None

    def other_arm_step(self, scheduled: ScheduledStep) -> Optional[PlanStep]:
        """
        :param scheduled: A step.
        :return: The step naming the arm of the robot other than the one its grounding
            chose, when it leaves its arm to be chosen between a left and a right one;
            else None.
        """
        arguments = StepArguments(
            context=self.context,
            bodies=self.bodies,
            action=self.actions.named(scheduled.step.action),
            step=scheduled.step,
            site=self.site,
        )
        open_field = arguments.find_open_arm_field()
        if open_field is None:
            return None
        chosen = ENUM_NAMES.member(Arms, scheduled.resolved.values[open_field])
        others = {Arms.LEFT: Arms.RIGHT, Arms.RIGHT: Arms.LEFT}
        if chosen not in others:
            return None
        return replace(
            scheduled.step,
            values={
                **scheduled.step.values,
                open_field: ENUM_NAMES.member_identifier(Arms, others[chosen]),
            },
        )

    def redetection(self, scheduled: ScheduledStep) -> StatechartNode:
        """
        :param scheduled: A step.
        :return: The detection, on the robot's table, of each object the step expects in
            place, by its kind and the color it shows.
        """
        table = RegionBoxes(self.context.robot, site=self.site).box(DetectionRegion())
        detections = []
        for identifier in scheduled.expected_positions:
            body = self.bodies[identifier]
            colors = body.visual.color_names()
            detections.append(
                DetectAction(
                    technique=DetectionTechnique.TYPES,
                    object_sem_annotation=type(PlannedGraspable.of(body)),
                    detection_box=table,
                    color=next(iter(colors)) if len(colors) == 1 else None,
                    accept_first_if_multiple=True,
                )
            )
        return StepSequence(nodes=detections)
