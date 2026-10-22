"""
The PR2 demos in the workshop, recorded as task demos: fetching the screw box and
inserting a screw into the pilot hole, and the whole two-handed assembly that drives the
screw with the screwdriver.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import numpy as np
from typing_extensions import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from coraplex.datastructures.dataclasses import Context, MotionToleranceConfig
from coraplex.datastructures.enums import Arms, ApproachDirection, VerticalAlignment
from coraplex.plans.factories import sequential
from coraplex.plans.plan import Plan
from coraplex.plans.plan_callbacks import PlanCallback
from coraplex.robot_plans.actions.base import ActionDescription
from coraplex.robot_plans.actions.core.placing import PlaceAction
from cramera_cram.documents import DocumentFile
from cramera_cram.exceptions import TaskFailed
from cramera_cram.robot_task import RobotTaskDemo, TaskCommand
from cramera_cram.scenes.presentation import ScenePresentation
from cramera_protocol.bundle.acceptance import AcceptanceMetrics
from cramera_protocol.bundle.files import BundleFile
from cramera_protocol.bundle.scene import SceneDescription
from cramera_protocol.live_messages import SavedScene
from cramera_protocol.workshop import WorkshopSceneKey
from cramera_workshop.acceptance import (
    ACTION_SUCCEEDED,
    ASSEMBLY_TOLERANCES,
    AssemblyStage,
    ContentsMeasurement,
    DemoMeasurement,
    Requirement,
)
from cramera_workshop.bundle import WorkshopBundle, WorkshopFile
from cramera_workshop.physics import WorkshopPhysics
from cramera_workshop.robot.contents import ContentsMeasurements, WorkshopContents
from cramera_workshop.robot.gaze import AnchoredToolCenterPointMotion
from cramera_workshop.robot.grasps import DriverGrasp, ScrewGrasp
from cramera_workshop.robot.navigation import WorkshopTranslateAction
from cramera_workshop.robot.pickup import PickUpDriverAction, PickUpLooseScrewAction
from cramera_workshop.robot.screw_thread import (
    AlignScrewdriverAction,
    DriveScrewAction,
    EngageScrewAction,
    ReleaseScrewSupportAction,
    ThreadDimensions,
)
from cramera_workshop.robot.transport import (
    MoveHeldObjectAction,
    RetrieveScrewBoxAction,
)
from cramera_workshop.robot.world import RobotStart, WorkshopBody, WorkshopEnvironment
from giskardpy.motion_statechart.motion_statechart import MotionStatechart
from semantic_digital_twin.collision_checking.collision_rules import (
    AllowCollisionBetweenGroups,
    AvoidCollisionBetweenGroups,
)
from semantic_digital_twin.datastructures.definitions import (
    StaticJointState,
    TorsoState,
)
from semantic_digital_twin.robots.pr2 import PR2
from semantic_digital_twin.spatial_types import Pose
from semantic_digital_twin.world import World
from semantic_digital_twin.world_description.world_entity import Body

# %% names


class WorkshopDemoName(StrEnum):
    """
    The recordings the demos are saved as, and the parts of their names.
    """

    ROBOT = "pr2"
    """
    The robot's part of a recording's name.
    """

    INSERTION = "screw_insertion"
    """
    The insertion demo's part of its recording's name.
    """

    ASSEMBLY = "screw_assembly"
    """
    The assembly demo's part of its recording's name.
    """


# %% acceptance


@dataclass
class ExecutionObservation(PlanCallback):
    """
    Counts the control periods and measures the smallest collision distance while the
    plan runs; it measures, it moves nothing.
    """

    context: Context = field(kw_only=True)
    """
    The world and robot being checked.
    """

    ticks: int = field(default=0, init=False)
    """
    How many control periods ran.
    """

    minimum_distance: Optional[float] = field(default=None, init=False)
    """
    The smallest collision distance measured, in metres; None while no contact was
    within reach.
    """

    def on_motion_tick(self, statechart: MotionStatechart) -> None:
        self.ticks += 1
        contacts = self.context.world.collision_manager.compute_collisions().contacts
        distances = [float(contact.distance) for contact in contacts]
        if self.minimum_distance is not None:
            distances.append(self.minimum_distance)
        if distances:
            self.minimum_distance = min(distances)


# %% demo base


@dataclass
class WorkshopTaskDemo(RobotTaskDemo):
    """
    A PR2 task in the workshop: the collision rules, gaze-following tool motions and
    tolerances the workshop's small parts need, the screw box's loose contents in a
    contact world, and the assets' rights on the saved recording.
    """

    bundle: WorkshopBundle = field(
        default_factory=WorkshopBundle.packaged, kw_only=True
    )
    """
    The workshop bundle.
    """

    arm_clearance: float = field(default=0.02, kw_only=True)
    """
    The clearance the arm keeps from the furniture, in metres.
    """

    gripper_clearance: float = field(default=0.001, kw_only=True)
    """
    The clearance the gripper and a carried screw keep, in metres.
    """

    position_tolerance: float = field(default=0.0005, kw_only=True)
    """
    How close the tool must come to its target, in metres.
    """

    orientation_tolerance: float = field(default=0.003, kw_only=True)
    """
    How close the tool's orientation must come, in radians.
    """

    control_period: float = field(default=0.02, kw_only=True)
    """
    The simulated time of one control period, in seconds.
    """

    bench_base: RobotStart = field(
        default_factory=lambda: RobotStart(x=0.16, y=-0.86), kw_only=True
    )
    """
    Where the base stands in front of the assembly station.
    """

    contents: Optional[WorkshopContents] = field(default=None, init=False)
    """
    The box's contents, coupled while the box is carried.
    """

    observation: Optional[ExecutionObservation] = field(default=None, init=False)
    """
    What the run measured while the plan ran.
    """

    actions: List[ActionDescription] = field(default_factory=list, init=False)
    """
    The plan's top-level actions.
    """

    @classmethod
    def of_bundle(
        cls, bundle: WorkshopBundle, task_identifier: str, task: str, **fields: Any
    ) -> WorkshopTaskDemo:
        """
        :param bundle: The workshop bundle.
        :param task_identifier: The task's part of the recording's name.
        :param task: What the task does, as the scene picker labels it.
        :param fields: The other fields of the demo.
        :return: The demo, recorded as ``<bundle>_pr2_<task identifier>`` beside the
            workshop, with its appearance.
        """
        return cls(
            environment=WorkshopEnvironment(bundle=bundle),
            robot=RobotStart(x=1.65, y=-0.86).pr2(),
            name="_".join((bundle.scene.name, WorkshopDemoName.ROBOT, task_identifier)),
            task=task,
            environment_name=bundle.scene.environment_name,
            presentation=ScenePresentation.of_bundle(bundle.directory),
            bundle=bundle,
            **fields,
        )

    # %% context

    def build_context(self, world: World) -> Context:
        context = super().build_context(world)
        robot = context.robot
        for arm in (robot.left_arm, robot.right_arm):
            arm.get_joint_state_by_type(StaticJointState.PARK).apply_to(world)
        robot.get_torso().get_joint_state_by_type(TorsoState.HIGH).apply_to(world)
        self.add_collision_rules(world, robot)
        return Context(
            world=world,
            robot=robot,
            alternative_motion_mappings=[AnchoredToolCenterPointMotion],
            motion_tolerances=MotionToleranceConfig(
                default_tcp_position_threshold=self.position_tolerance,
                tool_orientation_threshold=self.orientation_tolerance,
            ),
        )

    def add_collision_rules(self, world: World, robot: PR2) -> None:
        """
        Allow the contacts manipulation needs and keep the arms clear of the furniture.

        :param world: The world.
        :param robot: The PR2.
        """
        screws = self.environment.screws(world)
        box = world.get_body_by_name(WorkshopBody.SCREW_BOX)
        handle = world.get_body_by_name(WorkshopBody.SCREW_BOX_HANDLE)
        driver = world.get_body_by_name(WorkshopBody.DRIVER)
        workpiece = world.get_body_by_name(WorkshopBody.ASSEMBLY)
        left = robot.left_arm
        right = robot.right_arm
        left_gripper = left.end_effector.bodies_with_collision
        held = {driver, *screws}
        obstacles = [
            body
            for body in world.bodies
            if body not in robot.bodies and body.collision and body not in held
        ]
        allowed = [
            ([robot.mobile_base.root], [world.get_body_by_name(WorkshopBody.FLOOR)]),
            (left_gripper, screws),
            ([box, handle], screws),
            (left_gripper, [box, handle]),
            (right.end_effector.bodies_with_collision, [driver]),
            (screws, [workpiece]),
            ([driver], screws),
        ]
        avoided = [
            (
                [
                    body
                    for body in left.bodies_with_collision
                    if body not in left_gripper
                ],
                obstacles,
                self.arm_clearance,
            ),
            (left_gripper, obstacles, self.gripper_clearance),
            (right.bodies_with_collision, obstacles, self.gripper_clearance),
            (screws, obstacles, self.gripper_clearance),
        ]
        with world.modify_world():
            for first, second in allowed:
                world.collision_manager.add_ignore_collision_rule(
                    AllowCollisionBetweenGroups(body_group_a=first, body_group_b=second)
                )
            for first, second, clearance in avoided:
                world.collision_manager.add_default_rule(
                    AvoidCollisionBetweenGroups(
                        body_group_a=first,
                        body_group_b=second,
                        buffer_zone_distance=clearance,
                        violated_distance=0.0,
                    )
                )

    # %% plan

    def build_plan(self, context: Context) -> Plan:
        self.actions = self.plan_actions(context)
        retrieval = self.actions[0]
        self.contents = WorkshopContents(
            world=context.world,
            physics=WorkshopPhysics(self.bundle),
            control_period=self.control_period,
            box=retrieval.box,
            contents=retrieval.screws,
            action=retrieval,
        )
        self.contents.start()
        self.observation = ExecutionObservation(context=context)
        plan = sequential(self.actions, context=context).plan
        plan.node_callbacks.extend([self.contents, self.observation])
        return plan

    def plan_actions(self, context: Context) -> List[ActionDescription]:
        """
        :param context: The world and robot.
        :return: The plan's top-level actions; the first fetches the screw box.
        """
        return [self.retrieval(context)]

    def retrieval(self, context: Context) -> RetrieveScrewBoxAction:
        """
        :param context: The world and robot.
        :return: Fetching the screw box to its bench pose.
        """
        world = context.world
        boxes = {item.key: item for item in self.bundle.workshop.bins}
        return RetrieveScrewBoxAction(
            world.get_body_by_name(WorkshopBody.SCREW_BOX),
            tuple(self.environment.screws(world)),
            self.environment.pose_of(world, boxes[WorkshopBody.SCREW_BOX].bench_pose),
            self.bench_base.world_pose(world),
        )

    def screw_pickup(self, context: Context, screw: Body) -> PickUpLooseScrewAction:
        """
        :param context: The world and robot.
        :param screw: The screw to pick up from the set-down box.
        :return: Picking it up with the left hand.
        """
        grasp = ScrewGrasp(
            ApproachDirection.FRONT,
            VerticalAlignment.NoAlignment,
            context.robot.left_arm.end_effector,
            manipulation_offset=0.12,
            shaft_offset=0.11,
        )
        return PickUpLooseScrewAction(
            screw,
            Arms.LEFT,
            grasp,
            pre_approach_linear_velocity=0.08,
            final_approach_linear_velocity=0.02,
            lift_linear_velocity=0.04,
        )

    def station_approach(self, context: Context) -> WorkshopTranslateAction:
        """
        :param context: The world and robot.
        :return: Moving sideways to the assembly station.
        """
        return WorkshopTranslateAction(
            Pose.from_xyz_rpy(
                0.35, self.bench_base.y, reference_frame=context.world.root
            )
        )

    # %% measurement

    def action_statuses(self) -> List[str]:
        """
        :return: The name of each top-level action's life-cycle value.
        """
        return [action.plan_node.status.name for action in self.actions]

    def box_position_error(self, context: Context) -> float:
        """
        :param context: The world and robot.
        :return: How far the box ended from its bench pose, in metres.
        """
        retrieval = self.actions[0]
        return float(
            np.linalg.norm(
                retrieval.box.global_pose.to_np()[:3, 3]
                - retrieval.destination.to_np()[:3, 3]
            )
        )

    def common_measurements(self, context: Context) -> Dict[str, Any]:
        """
        :param context: The world and robot.
        :return: What every workshop demo measures.
        """
        measurements = {
            DemoMeasurement.ACTION_STATUSES.value: self.action_statuses(),
            DemoMeasurement.BOX_POSITION_ERROR.value: self.box_position_error(context),
            DemoMeasurement.CONTROL_TICKS.value: self.observation.ticks,
            DemoMeasurement.CONTENTS.value: ContentsDocument(
                self.contents.measurements
            ).json(),
        }
        if self.observation.minimum_distance is not None:
            measurements[DemoMeasurement.MINIMUM_COLLISION_DISTANCE.value] = (
                self.observation.minimum_distance
            )
        return measurements

    def require(
        self, measurements: Dict[str, Any], conditions: Dict[Requirement, bool]
    ) -> AcceptanceMetrics:
        """
        :param measurements: What the run measured.
        :param conditions: Each requirement by what it requires.
        :return: The measurements as acceptance metrics.
        :raises TaskFailed: When a requirement does not hold.
        """
        failed = [
            requirement.value for requirement, holds in conditions.items() if not holds
        ]
        if failed:
            raise TaskFailed("; ".join(failed))
        return AcceptanceMetrics(measurements=measurements)

    def common_conditions(
        self, measurements: Dict[str, Any]
    ) -> Dict[Requirement, bool]:
        """
        :param measurements: What the run measured.
        :return: What every workshop demo requires.
        """
        tolerances = ASSEMBLY_TOLERANCES
        distance = measurements.get(DemoMeasurement.MINIMUM_COLLISION_DISTANCE)
        return {
            Requirement.ACTIONS_SUCCEEDED: all(
                status == ACTION_SUCCEEDED
                for status in measurements[DemoMeasurement.ACTION_STATUSES]
            ),
            Requirement.BOX_ON_BENCH: measurements[DemoMeasurement.BOX_POSITION_ERROR]
            < tolerances.box_position,
            Requirement.NO_PENETRATION: distance is None
            or distance >= -tolerances.penetration,
            Requirement.CONTENTS_RETAINED: self.contents.measurements.retained_contents,
        }

    # %% saving

    def complete(self, bundle: Path, metrics: AcceptanceMetrics) -> None:
        super().complete(bundle, metrics)
        scene_file = DocumentFile(bundle / BundleFile.SCENE)
        scene = scene_file.read(SceneDescription)
        rights = self.bundle.asset_rights
        scene.extensions[WorkshopSceneKey.ASSET_RIGHTS] = rights.to_json()
        scene_file.write(scene)
        for name in (rights.license_file, rights.notice_file, WorkshopFile.RIGHTS):
            shutil.copyfile(self.bundle.file(name), bundle / name)


@dataclass(frozen=True)
class ContentsDocument:
    """
    The contents' measurements as a JSON object of the acceptance metrics.
    """

    measurements: ContentsMeasurements
    """
    The measurements.
    """

    def json(self) -> Dict[str, Any]:
        """
        :return: The measurements by :class:`ContentsMeasurement` name.
        """
        measured = self.measurements
        return {
            ContentsMeasurement.MODEL.value: measured.model.value,
            ContentsMeasurement.TICKS.value: measured.ticks,
            ContentsMeasurement.SIMULATED_SECONDS.value: measured.simulated_seconds,
            ContentsMeasurement.MAXIMUM_BOX_POSITION_LAG.value: measured.maximum_box_position_lag,
            ContentsMeasurement.MAXIMUM_BOX_ANGULAR_LAG.value: measured.maximum_box_angular_lag,
            ContentsMeasurement.MAXIMUM_RELATIVE_DISPLACEMENT.value: measured.maximum_relative_displacement,
            ContentsMeasurement.MAXIMUM_PROJECTION_CORRECTION.value: measured.maximum_projection_correction,
            ContentsMeasurement.RETAINED_CONTENTS.value: measured.retained_contents,
            ContentsMeasurement.ESCAPED_CONTENTS.value: list(measured.escaped_contents),
            ContentsMeasurement.CONTENTS_COUNT.value: measured.contents_count,
        }


# %% insertion


@dataclass
class ScrewInsertionDemo(WorkshopTaskDemo):
    """
    Fetches the screw box, picks up a screw and holds its tip at the pilot hole's
    entrance.
    """

    def plan_actions(self, context: Context) -> List[ActionDescription]:
        world = context.world
        screw = world.get_body_by_name(WorkshopBody.SCREW)
        return [
            self.retrieval(context),
            self.screw_pickup(context, screw),
            self.station_approach(context),
            MoveHeldObjectAction(
                screw, self.environment.pilot_mouth(world), keep_shaft_roll=True
            ),
        ]

    def measure(self, context: Context) -> AcceptanceMetrics:
        world = context.world
        screw = world.get_body_by_name(WorkshopBody.SCREW)
        error = float(
            np.linalg.norm(
                screw.global_pose.to_np()[:3, 3]
                - self.environment.pilot_mouth(world).to_np()[:3, 3]
            )
        )
        measurements = self.common_measurements(context)
        measurements[DemoMeasurement.SCREW_POSITION_ERROR.value] = error
        conditions = self.common_conditions(measurements)
        conditions[Requirement.SCREW_AT_PILOT] = (
            error < ASSEMBLY_TOLERANCES.screw_position
        )
        return self.require(measurements, conditions)


# %% assembly


@dataclass
class ScrewAssemblyDemo(WorkshopTaskDemo):
    """
    The whole assembly: fetch the screw box, pick a screw with the left hand, pick the
    screwdriver with the right, hold the screw at the pilot hole, seat the blade, engage
    the thread, let go with the left hand, drive the screw in and put the screwdriver
    back.
    """

    def plan_actions(self, context: Context) -> List[ActionDescription]:
        world = context.world
        screw = world.get_body_by_name(WorkshopBody.SCREW)
        driver = world.get_body_by_name(WorkshopBody.DRIVER)
        workpiece = world.get_body_by_name(WorkshopBody.ASSEMBLY)
        dimensions = ThreadDimensions.of_workshop(self.bundle.workshop)
        driver_grasp = DriverGrasp(
            ApproachDirection.FRONT,
            VerticalAlignment.NoAlignment,
            context.robot.right_arm.end_effector,
        )
        return [
            self.retrieval(context),
            self.screw_pickup(context, screw),
            self.station_approach(context),
            PickUpDriverAction(
                driver,
                Arms.RIGHT,
                driver_grasp,
                pre_approach_linear_velocity=0.08,
                final_approach_linear_velocity=0.02,
                lift_linear_velocity=0.04,
            ),
            MoveHeldObjectAction(
                screw, self.environment.pilot_mouth(world), keep_shaft_roll=True
            ),
            AlignScrewdriverAction(screw, driver, dimensions),
            EngageScrewAction(screw, driver, workpiece, dimensions),
            ReleaseScrewSupportAction(screw),
            DriveScrewAction(screw, driver),
            PlaceAction(
                driver,
                self.environment.pose_of(world, self.bundle.workshop.driver.home),
                Arms.RIGHT,
                transport_linear_velocity=0.07,
                placing_linear_velocity=0.025,
            ),
        ]

    def measure(self, context: Context) -> AcceptanceMetrics:
        world = context.world
        screw = world.get_body_by_name(WorkshopBody.SCREW)
        driver = world.get_body_by_name(WorkshopBody.DRIVER)
        workpiece = world.get_body_by_name(WorkshopBody.ASSEMBLY)
        dimensions = ThreadDimensions.of_workshop(self.bundle.workshop)
        workpiece_T_screw = world.compute_forward_kinematics_np(workpiece, screw)
        depth = float(dimensions.mouth_height - workpiece_T_screw[2, 3])
        support = context.robot.left_arm.end_effector.tool_frame
        support_distance = float(
            np.linalg.norm(
                support.global_pose.to_np()[:3, 3] - screw.global_pose.to_np()[:3, 3]
            )
        )
        measurements = self.common_measurements(context)
        measurements.update(
            {
                DemoMeasurement.SCREW_DEPTH.value: depth,
                DemoMeasurement.REQUIRED_DEPTH.value: dimensions.depth,
                DemoMeasurement.DRIVER_RELEASED.value: driver.parent_connection.parent
                is world.root,
                DemoMeasurement.SUPPORT_RELEASED.value: support_distance
                > ASSEMBLY_TOLERANCES.support_clearance,
            }
        )
        conditions = self.common_conditions(measurements)
        conditions.update(
            {
                Requirement.ALL_STAGES: len(self.actions) == len(AssemblyStage),
                Requirement.SCREW_DRIVEN: abs(depth - dimensions.depth)
                < ASSEMBLY_TOLERANCES.depth,
                Requirement.DRIVER_PUT_DOWN: measurements[
                    DemoMeasurement.DRIVER_RELEASED
                ],
                Requirement.SUPPORT_WITHDRAWN: measurements[
                    DemoMeasurement.SUPPORT_RELEASED
                ],
            }
        )
        return self.require(measurements, conditions)


# %% command line

DEMO_TASKS: Mapping[WorkshopDemoName, Tuple[type, str]] = {
    WorkshopDemoName.INSERTION: (
        ScrewInsertionDemo,
        "PR2: fetch the screw box and insert a screw into the pilot hole",
    ),
    WorkshopDemoName.ASSEMBLY: (
        ScrewAssemblyDemo,
        "PR2: fetch the screw box and drive a screw with both hands",
    ),
}
"""
Each demo's class and what its task does, as the scene picker labels it.
"""


@dataclass(frozen=True)
class WorkshopDemoCommand:
    """
    The command line of one workshop demo in the packaged workshop.
    """

    name: WorkshopDemoName
    """
    The demo.
    """

    def main(self, arguments: Sequence[str]) -> SavedScene:
        """
        :param arguments: The demo command's arguments.
        :return: The saved or published recording.
        """
        demo_class, task = DEMO_TASKS[self.name]
        demo = demo_class.of_bundle(WorkshopBundle.packaged(), self.name.value, task)
        return TaskCommand(demo).main(arguments)
